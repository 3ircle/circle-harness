// DeepSeek to Localhost Bridge - Content Script
(function () {
  'use strict';

  console.log('%c[DeepSeek Bridge] Loaded on chat.deepseek.com', 'background: #2563eb; color: #fff; padding: 3px 8px; border-radius: 4px;');

  const sentMessageHashes = new Set();
  let lastObservedLength = 0;
  let textStabilityTimer = null;
  let latestExtractedMessage = null;
  let isCurrentlyStreaming = false;

  let appSettings = {
    serverUrl: 'http://localhost:8000/chat/',
    autoSend: true,
    includeThinking: true
  };

  // 1. Load initial settings
  chrome.runtime.sendMessage({ action: 'GET_SETTINGS' }, (res) => {
    if (res) {
      appSettings = { ...appSettings, ...res };
      updateAllToggleUI();
      console.log('[DeepSeek Bridge] Settings loaded:', appSettings);
    }
  });

  // 2. Listen for settings changes across extension
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.serverUrl) appSettings.serverUrl = changes.serverUrl.newValue;
    if (changes.autoSend !== undefined) {
      appSettings.autoSend = changes.autoSend.newValue;
      updateAllToggleUI();
    }
    if (changes.includeThinking !== undefined) appSettings.includeThinking = changes.includeThinking.newValue;
  });

  function hashString(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return String(hash) + '_' + str.length;
  }

  function showToast(text, type = 'info', duration = 3500) {
    let toast = document.getElementById('ds-bridge-toast-elem');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'ds-bridge-toast-elem';
      toast.className = 'ds-bridge-toast';
      document.body.appendChild(toast);
    }

    toast.className = `ds-bridge-toast ${type} show`;
    toast.textContent = text;

    clearTimeout(toast.__timeout);
    toast.__timeout = setTimeout(() => {
      toast.classList.remove('show');
    }, duration);
  }

  // 3. Send message payload to background service worker (which POSTs to localhost)
  async function dispatchMessageToServer(messageData, isManual = false) {
    if (!messageData || !messageData.message || messageData.message.trim().length === 0) {
      if (isManual) showToast('متنی برای ارسال یافت نشد', 'error');
      return;
    }

    const cleanMsg = messageData.message.trim();
    const hash = hashString(cleanMsg);

    if (!isManual && sentMessageHashes.has(hash)) {
      console.log('[DeepSeek Bridge] Message already sent, skipping duplicate hash.');
      return;
    }

    setWidgetState('busy');
    console.log('%c[DeepSeek Bridge] Sending COMPLETED message to server...', 'color: #3b82f6; font-weight: bold;', cleanMsg.substring(0, 100));

    const payload = {
      message: cleanMsg,
      thinking: messageData.thinking || null,
      role: 'assistant',
      model: messageData.model || 'deepseek',
      manual: isManual,
      url: window.location.href,
      timestamp: new Date().toISOString()
    };

    chrome.runtime.sendMessage({ action: 'SEND_CHAT', data: payload }, (response) => {
      if (chrome.runtime.lastError || !response || !response.success) {
        const errMsg = (response && response.error) || (chrome.runtime.lastError && chrome.runtime.lastError.message) || 'ارتباط با سرور برقرار نشد';
        console.error('[DeepSeek Bridge] Send failed:', errMsg, response);
        setWidgetState('offline');
        showToast(`خطا در ارسال به ${payload.url || 'localhost'}: ${errMsg}`, 'error', 4500);
      } else {
        console.log('%c[DeepSeek Bridge] Successfully received by server! (Status: ' + response.status + ')', 'color: #10b981; font-weight: bold;');
        sentMessageHashes.add(hash);
        latestExtractedMessage = messageData;
        setWidgetState('online');
        const preview = cleanMsg.length > 40 ? cleanMsg.substring(0, 40) + '...' : cleanMsg;
        showToast(`✓ پیام کامل به سرور ارسال شد (${preview})`, 'success');
      }
    });
  }

  // 4. Stream intercept from inject.js (Network layer)
  window.addEventListener('message', (event) => {
    if (event.source !== window || !event.data) return;

    if (event.data.type === 'DEEPSEEK_BRIDGE_STREAM_COMPLETE') {
      const payload = event.data.payload;
      console.log('[DeepSeek Bridge] Network SSE stream completed.');
      if (payload && payload.message) {
        latestExtractedMessage = payload;
        if (appSettings.autoSend) {
          // Verify generation is not currently active on DOM
          setTimeout(() => {
            if (!isGeneratingActive()) {
              dispatchMessageToServer(payload, false);
            }
          }, 500);
        }
      }
    }
  });

  // --- Generation & Completion Detection ---

  // Checks if DeepSeek is CURRENTLY generating text (Stop button or cursor active)
  function isGeneratingActive() {
    // 1. Check for Stop generation button anywhere
    const buttons = document.querySelectorAll('button, div[role="button"]');
    for (const b of buttons) {
      const aria = (b.getAttribute('aria-label') || '').toLowerCase();
      const txt = (b.textContent || '').toLowerCase();
      if (aria.includes('stop') || txt.includes('stop') || txt.includes('توقف') || txt.includes('停止')) {
        return true;
      }
      // Square/rect inside button SVG indicates Stop button
      if (b.querySelector('svg rect')) {
        return true;
      }
    }

    // 2. Check for blinking streaming cursor element
    if (document.querySelector('.ds-cursor, [class*="ds-cursor"], [class*="blinking-cursor"]')) {
      return true;
    }

    return false;
  }

  // Checks if an assistant message container is 100% finished
  function isMessageFullyCompleted(container) {
    if (!container) return false;

    // If stop button is visible on page, generation is NOT finished
    if (isGeneratingActive()) {
      return false;
    }

    // In DeepSeek, the Copy button only renders once the response has completely finished generating!
    const copyBtn = container.querySelector('[aria-label*="Copy"], [aria-label*="کپی"], [title*="Copy"], [title*="کپی"], svg[class*="copy"]');
    if (copyBtn) {
      return true;
    }

    // Alternative: check if action bar (like thumbs up/down, retry) has rendered
    const actionGroup = container.querySelector('[class*="action"], [class*="tool"], [class*="operate"], [class*="button-group"]');
    if (actionGroup && actionGroup.children.length >= 2) {
      return true;
    }

    return false;
  }

  // Extract clean text and reasoning from an assistant message container
  function extractAssistantMessage(container) {
    if (!container) return null;

    // Look for markdown content element
    const mdEl = container.matches('.ds-markdown, [class*="ds-markdown"], [class*="markdown"], [class*="prose"]')
      ? container
      : container.querySelector('.ds-markdown, [class*="ds-markdown"], [class*="markdown"], [class*="prose"]');

    // Look for reasoning/thinking block (DeepSeek R1)
    let thinking = null;
    const thinkEl = container.querySelector('[class*="ds-think"], [class*="think"], details, [class*="reasoning"]');
    if (thinkEl) {
      thinking = thinkEl.innerText.trim();
    }

    let messageText = '';
    if (mdEl) {
      const clone = mdEl.cloneNode(true);
      // Remove thinking element from main body if nested
      const innerThink = clone.querySelector('[class*="ds-think"], [class*="think"], details, [class*="reasoning"]');
      if (innerThink) innerThink.remove();
      // Remove our injected extension buttons
      clone.querySelectorAll('.ds-bridge-msg-btn').forEach(el => el.remove());
      messageText = clone.innerText.trim();
    } else {
      const clone = container.cloneNode(true);
      clone.querySelectorAll('.ds-bridge-msg-btn').forEach(el => el.remove());
      messageText = clone.innerText.trim();
    }

    if (!messageText) return null;

    return {
      message: messageText,
      thinking: thinking,
      role: 'assistant',
      source: 'dom'
    };
  }

  // Find all assistant message elements in the chat
  function getAllAssistantContainers() {
    const mdElements = document.querySelectorAll('.ds-markdown, [class*="ds-markdown"], [class*="markdown"], [class*="prose"]');
    const list = [];

    mdElements.forEach(md => {
      const wrapper = md.closest('[class*="message"], [class*="chat-item"], [class*="talk-item"]') || md.parentElement || md;
      if (!list.includes(wrapper)) {
        list.push(wrapper);
      }
    });

    if (list.length === 0) {
      const potentialItems = document.querySelectorAll('[class*="message"], [class*="talk"]');
      potentialItems.forEach(item => {
        const className = item.className || '';
        if (!className.includes('user') && item.innerText.trim().length > 0) {
          list.push(item);
        }
      });
    }

    return list;
  }

  // --- Input Bar Pill Toggle (beside DeepThink / Search) ---
  function injectInputToolbarToggle() {
    const existingToggle = document.getElementById('ds-bridge-auto-toggle');
    if (existingToggle) {
      // Sync active state
      if (appSettings.autoSend && !existingToggle.classList.contains('active')) {
        existingToggle.classList.add('active');
        const text = existingToggle.querySelector('.ds-bridge-toggle-text');
        if (text) text.textContent = 'ارسال خودکار: روشن';
      } else if (!appSettings.autoSend && existingToggle.classList.contains('active')) {
        existingToggle.classList.remove('active');
        const text = existingToggle.querySelector('.ds-bridge-toggle-text');
        if (text) text.textContent = 'ارسال خودکار: خاموش';
      }
      return;
    }

    // Locate DeepSeek toolbar row (where DeepThink and Search pills live)
    let targetContainer = null;
    let insertAfterEl = null;

    // Search by text "DeepThink" or "Search"
    const allButtons = document.querySelectorAll('button, div[role="button"], span');
    for (const el of allButtons) {
      const txt = (el.textContent || '').trim();
      if (txt === 'DeepThink' || txt === 'Search' || txt.includes('DeepThink') || txt.includes('Search')) {
        const btn = el.closest('button') || el.closest('[role="button"]') || el;
        if (btn && btn.parentElement) {
          targetContainer = btn.parentElement;
          // Prefer inserting right after Search
          if (txt.includes('Search')) {
            insertAfterEl = btn;
            break;
          } else {
            insertAfterEl = btn;
          }
        }
      }
    }

    // Fallback: look near chat textarea
    if (!targetContainer) {
      const textarea = document.querySelector('textarea, [contenteditable="true"]');
      if (textarea) {
        const form = textarea.closest('form') || textarea.parentElement?.parentElement;
        if (form) {
          const row = form.querySelector('[class*="tool"], [class*="footer"], [class*="action"], [class*="bottom"]');
          if (row) targetContainer = row;
        }
      }
    }

    if (!targetContainer) return;

    // Create the pill toggle button
    const toggleBtn = document.createElement('button');
    toggleBtn.id = 'ds-bridge-auto-toggle';
    toggleBtn.className = 'ds-bridge-pill-toggle ' + (appSettings.autoSend ? 'active' : '');
    toggleBtn.type = 'button';
    toggleBtn.title = 'ارسال خودکار پیام‌های کامل شده به localhost:8000/chat/ (کلیک برای تغییر)';

    toggleBtn.innerHTML = `
      <svg class="ds-bridge-pill-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
      </svg>
      <span class="ds-bridge-toggle-text">${appSettings.autoSend ? 'ارسال خودکار: روشن' : 'ارسال خودکار: خاموش'}</span>
      <span class="ds-bridge-pill-dot"></span>
    `;

    toggleBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();

      appSettings.autoSend = !appSettings.autoSend;

      // Update button visual
      toggleBtn.className = 'ds-bridge-pill-toggle ' + (appSettings.autoSend ? 'active' : '');
      const textSpan = toggleBtn.querySelector('.ds-bridge-toggle-text');
      if (textSpan) {
        textSpan.textContent = appSettings.autoSend ? 'ارسال خودکار: روشن' : 'ارسال خودکار: خاموش';
      }

      // Save to chrome storage
      chrome.storage.local.set({ autoSend: appSettings.autoSend });

      // Sync floating widget checkbox
      const autoCheckbox = document.getElementById('ds-bridge-auto-checkbox');
      if (autoCheckbox) autoCheckbox.checked = appSettings.autoSend;

      if (appSettings.autoSend) {
        showToast('✓ ارسال خودکار پیام‌ها فعال شد (پیام‌ها پس از کامل شدن ارسال می‌شوند)', 'success');
      } else {
        showToast('ارسال خودکار پیام‌ها غیرفعال شد', 'info');
      }
    });

    if (insertAfterEl && insertAfterEl.nextSibling) {
      targetContainer.insertBefore(toggleBtn, insertAfterEl.nextSibling);
    } else {
      targetContainer.appendChild(toggleBtn);
    }

    console.log('[DeepSeek Bridge] Injected Auto-Send pill toggle in DeepSeek toolbar!');
  }

  // Update all toggle UIs across page
  function updateAllToggleUI() {
    const pillToggle = document.getElementById('ds-bridge-auto-toggle');
    if (pillToggle) {
      pillToggle.className = 'ds-bridge-pill-toggle ' + (appSettings.autoSend ? 'active' : '');
      const textSpan = pillToggle.querySelector('.ds-bridge-toggle-text');
      if (textSpan) {
        textSpan.textContent = appSettings.autoSend ? 'ارسال خودکار: روشن' : 'ارسال خودکار: خاموش';
      }
    }
    const autoCheckbox = document.getElementById('ds-bridge-auto-checkbox');
    if (autoCheckbox) {
      autoCheckbox.checked = appSettings.autoSend;
    }
    updateWidgetStatus();
  }

  // --- Manual In-Message Button ---
  function injectMessageButtons() {
    const containers = getAllAssistantContainers();

    containers.forEach((container) => {
      if (container.querySelector('.ds-bridge-msg-btn')) return;

      const btn = document.createElement('button');
      btn.className = 'ds-bridge-msg-btn';
      btn.type = 'button';
      btn.innerHTML = '🚀 ارسال به localhost';
      btn.title = 'ارسال دستی این پیام به localhost:8000/chat/';

      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();

        const data = extractAssistantMessage(container);
        if (!data || !data.message) {
          showToast('متن پیام استخراج نشد', 'error');
          return;
        }

        btn.disabled = true;
        btn.innerHTML = '⏳ در حال ارسال...';

        chrome.runtime.sendMessage({ action: 'SEND_CHAT', data: { ...data, manual: true } }, (res) => {
          btn.disabled = false;
          if (res && res.success) {
            btn.className = 'ds-bridge-msg-btn success';
            btn.innerHTML = '✓ ارسال شد';
            showToast('پیام به سرور ارسال شد', 'success');
            setTimeout(() => {
              btn.className = 'ds-bridge-msg-btn';
              btn.innerHTML = '🚀 ارسال به localhost';
            }, 3000);
          } else {
            btn.className = 'ds-bridge-msg-btn error';
            btn.innerHTML = '✗ خطا';
            const err = (res && res.error) || 'سرور پاسخ نداد';
            showToast(`خطا: ${err}`, 'error');
            setTimeout(() => {
              btn.className = 'ds-bridge-msg-btn';
              btn.innerHTML = '🚀 ارسال مجدد';
            }, 3000);
          }
        });
      });

      const targetBar = container.querySelector('[class*="action"], [class*="tool"], [class*="operate"], [class*="footer"]') ||
                        container.querySelector('button')?.parentElement;

      if (targetBar) {
        targetBar.appendChild(btn);
      } else {
        container.appendChild(btn);
      }
    });
  }

  // --- Main DOM Observer & Auto-Send Trigger ---
  function handleDomUpdate() {
    // 1. Ensure pill toggle is present in toolbar
    injectInputToolbarToggle();

    // 2. Ensure message action buttons are present
    injectMessageButtons();

    // 3. Monitor assistant messages
    const containers = getAllAssistantContainers();
    if (containers.length === 0) return;

    const latestContainer = containers[containers.length - 1];
    const data = extractAssistantMessage(latestContainer);
    if (!data || !data.message) return;

    const currentLength = data.message.length;
    latestExtractedMessage = data;

    const generating = isGeneratingActive();

    if (generating) {
      isCurrentlyStreaming = true;
      setWidgetState('busy');
      clearTimeout(textStabilityTimer);
      lastObservedLength = currentLength;
      return;
    }

    // Check if generation just finished or message is confirmed complete
    const isCompleted = isMessageFullyCompleted(latestContainer);

    if (currentLength !== lastObservedLength || isCurrentlyStreaming) {
      lastObservedLength = currentLength;
      clearTimeout(textStabilityTimer);

      // Wait for text stability (at least 1500ms after text stops growing)
      textStabilityTimer = setTimeout(() => {
        const stillGenerating = isGeneratingActive();
        if (!stillGenerating && currentLength > 0) {
          isCurrentlyStreaming = false;
          setWidgetState('online');
          console.log('[DeepSeek Bridge] Message text stabilized and verified complete. Length:', currentLength);

          if (appSettings.autoSend) {
            const freshData = extractAssistantMessage(latestContainer);
            if (freshData) {
              dispatchMessageToServer(freshData, false);
            }
          }
        }
      }, 1500);
    } else if (isCompleted) {
      // Copy button is present and not generating -> definitively complete!
      const hash = hashString(data.message.trim());
      if (appSettings.autoSend && !sentMessageHashes.has(hash)) {
        console.log('[DeepSeek Bridge] Full completion confirmed via Copy button. Sending...');
        clearTimeout(textStabilityTimer);
        isCurrentlyStreaming = false;
        setWidgetState('online');
        dispatchMessageToServer(data, false);
      }
    }
  }

  // Setup DOM Observer
  const observer = new MutationObserver(() => {
    handleDomUpdate();
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true
  });

  // --- Floating Status Widget ---
  function createFloatingWidget() {
    if (document.getElementById('ds-bridge-floating-widget')) return;

    const widget = document.createElement('div');
    widget.id = 'ds-bridge-floating-widget';
    widget.className = 'collapsed';

    widget.innerHTML = `
      <div class="ds-bridge-header" id="ds-bridge-header">
        <div class="ds-bridge-title">
          <span class="ds-bridge-dot" id="ds-bridge-dot"></span>
          <span>پل ارتباطی Localhost</span>
        </div>
        <button class="ds-bridge-toggle-btn" id="ds-bridge-collapse-btn">◀</button>
      </div>
      <div class="ds-bridge-body">
        <div class="ds-bridge-row">
          <span>آدرس مقصد:</span>
          <strong style="font-size:11px; color:#93c5fd;" id="ds-bridge-url-display">localhost:8000/chat/</strong>
        </div>
        <div class="ds-bridge-row">
          <span>ارسال خودکار:</span>
          <label style="cursor:pointer; display:flex; align-items:center; gap:4px;">
            <input type="checkbox" id="ds-bridge-auto-checkbox" ${appSettings.autoSend ? 'checked' : ''}>
            <span style="font-size:11.5px;">فعال</span>
          </label>
        </div>
        <button class="ds-bridge-btn" id="ds-bridge-send-last-btn">
          <span>🚀 ارسال آخرین پاسخ دیپ‌سیک</span>
        </button>
        <button class="ds-bridge-btn secondary" id="ds-bridge-test-btn">
          <span>🔄 بررسی اتصال سرور</span>
        </button>
      </div>
    `;

    document.body.appendChild(widget);

    const header = document.getElementById('ds-bridge-header');
    const collapseBtn = document.getElementById('ds-bridge-collapse-btn');
    const autoCheckbox = document.getElementById('ds-bridge-auto-checkbox');
    const sendLastBtn = document.getElementById('ds-bridge-send-last-btn');
    const testBtn = document.getElementById('ds-bridge-test-btn');

    header.addEventListener('click', () => {
      widget.classList.toggle('collapsed');
      collapseBtn.textContent = widget.classList.contains('collapsed') ? '◀' : '▼';
    });

    autoCheckbox.addEventListener('change', (e) => {
      appSettings.autoSend = e.target.checked;
      chrome.storage.local.set({ autoSend: e.target.checked });
      updateAllToggleUI();
      showToast(`ارسال خودکار: ${e.target.checked ? 'فعال شد' : 'غیرفعال شد'}`);
    });

    sendLastBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const containers = getAllAssistantContainers();
      if (containers.length > 0) {
        const lastEl = containers[containers.length - 1];
        const data = extractAssistantMessage(lastEl);
        if (data && data.message) {
          dispatchMessageToServer(data, true);
          return;
        }
      }
      if (latestExtractedMessage) {
        dispatchMessageToServer(latestExtractedMessage, true);
      } else {
        showToast('هیچ پیامی در صفحه یافت نشد', 'error');
      }
    });

    testBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      testBtn.disabled = true;
      testBtn.textContent = 'در حال بررسی...';
      chrome.runtime.sendMessage({ action: 'TEST_CONNECTION' }, (res) => {
        testBtn.disabled = false;
        testBtn.textContent = '🔄 بررسی اتصال سرور';
        if (res && res.connected) {
          setWidgetState('online');
          showToast(`سرور در دسترس است (${res.url}) - وضعیت ${res.status}`, 'success');
        } else {
          setWidgetState('offline');
          showToast(`خطا: سرور در دسترس نیست (${(res && res.error) || 'Timeout'})`, 'error');
        }
      });
    });

    updateWidgetStatus();
  }

  function setWidgetState(state) {
    const dot = document.getElementById('ds-bridge-dot');
    if (!dot) return;
    dot.className = 'ds-bridge-dot ' + (state === 'online' ? '' : state);
  }

  function updateWidgetStatus() {
    const urlDisplay = document.getElementById('ds-bridge-url-display');
    if (urlDisplay && appSettings.serverUrl) {
      try {
        const parsed = new URL(appSettings.serverUrl);
        urlDisplay.textContent = parsed.host + parsed.pathname;
      } catch (e) {
        urlDisplay.textContent = appSettings.serverUrl;
      }
    }
  }

  // Initialization
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      createFloatingWidget();
      injectInputToolbarToggle();
      injectMessageButtons();
    });
  } else {
    createFloatingWidget();
    injectInputToolbarToggle();
    injectMessageButtons();
  }

  // Run periodic check for toolbar in case SPA renders slowly
  const checkInterval = setInterval(() => {
    injectInputToolbarToggle();
    injectMessageButtons();
  }, 1000);

  // Initial connection ping
  setTimeout(() => {
    chrome.runtime.sendMessage({ action: 'TEST_CONNECTION' }, (res) => {
      if (res && res.connected) {
        setWidgetState('online');
        console.log('[DeepSeek Bridge] Localhost server online at', res.url);
      } else {
        setWidgetState('offline');
        console.warn('[DeepSeek Bridge] Localhost server offline:', res && res.error);
      }
    });
  }, 1500);

})();
