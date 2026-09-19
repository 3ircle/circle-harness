// DeepSeek to Localhost Bridge - Page Context Interceptor (world: MAIN)
(function () {
  'use strict';

  if (window.__DEEPSEEK_BRIDGE_INJECTED__) return;
  window.__DEEPSEEK_BRIDGE_INJECTED__ = true;

  console.log('[DeepSeek Bridge Interceptor] Initialized in page context.');

  const originalFetch = window.fetch;

  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);

    try {
      const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');

      // Identify DeepSeek chat completion or message stream endpoint
      const isChatCompletion = url.includes('/chat/completion') ||
                               url.includes('/api/v0/chat') ||
                               url.includes('/api/chat') ||
                               (url.includes('deepseek.com') && url.includes('completion'));

      if (isChatCompletion && response && response.body && !response.bodyUsed) {
        console.log('[DeepSeek Bridge Interceptor] Intercepted chat completion stream:', url);

        // Tee the stream so original continues to DeepSeek UI unaffected
        const [stream1, stream2] = response.body.tee();

        // Pass stream2 to our reader asynchronously
        readCompletionStream(stream2, url);

        // Return new response with stream1 to page
        return new Response(stream1, {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers
        });
      }
    } catch (err) {
      console.warn('[DeepSeek Bridge Interceptor] Stream intercept error (fallback to DOM):', err);
    }

    return response;
  };

  async function readCompletionStream(stream, requestUrl) {
    const reader = stream.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let accumulatedContent = '';
    let accumulatedThinking = '';
    let modelName = '';
    let sessionId = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep partial line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith(':')) continue;

          if (trimmed.startsWith('data:')) {
            const dataStr = trimmed.slice(5).trim();
            if (dataStr === '[DONE]') {
              continue;
            }

            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.model) modelName = parsed.model;
              if (parsed.session_id || parsed.chat_id) sessionId = parsed.session_id || parsed.chat_id;

              const choices = parsed.choices || [];
              if (choices.length > 0 && choices[0].delta) {
                const delta = choices[0].delta;
                if (delta.content) {
                  accumulatedContent += delta.content;
                }
                if (delta.reasoning_content) {
                  accumulatedThinking += delta.reasoning_content;
                }
              }
            } catch (e) {
              // Ignore partial or non-JSON SSE lines
            }
          }
        }
      }

      if (accumulatedContent || accumulatedThinking) {
        console.log('[DeepSeek Bridge Interceptor] Stream complete. Captured characters:', accumulatedContent.length);
        window.postMessage({
          type: 'DEEPSEEK_BRIDGE_STREAM_COMPLETE',
          payload: {
            message: accumulatedContent.trim(),
            thinking: accumulatedThinking.trim() || null,
            model: modelName || 'deepseek-chat',
            sessionId: sessionId || null,
            source: 'network-stream',
            timestamp: new Date().toISOString()
          }
        }, '*');
      }
    } catch (streamErr) {
      console.warn('[DeepSeek Bridge Interceptor] Error reading stream:', streamErr);
    }
  }
})();
