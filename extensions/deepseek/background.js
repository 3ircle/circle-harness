// DeepSeek to Localhost Bridge - Background Service Worker

const DEFAULT_SETTINGS = {
  serverUrl: 'http://localhost:8000/chat/',
  autoSend: true,
  includeThinking: true,
  history: []
};

// Initialize settings on installation or load
chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS));
  const updates = {};
  for (const [key, value] of Object.entries(DEFAULT_SETTINGS)) {
    if (current[key] === undefined) {
      updates[key] = value;
    }
  }
  if (current.serverUrl === 'http://localhost:8000/chat') {
    updates.serverUrl = 'http://localhost:8000/chat/';
  }
  if (Object.keys(updates).length > 0) {
    await chrome.storage.local.set(updates);
  }
  console.log('[DeepSeek Bridge] Background service worker initialized.');
});

// Helper to get settings
async function getSettings() {
  const data = await chrome.storage.local.get(['serverUrl', 'autoSend', 'includeThinking', 'history']);
  let serverUrl = data.serverUrl || DEFAULT_SETTINGS.serverUrl;
  return {
    serverUrl,
    autoSend: data.autoSend !== undefined ? data.autoSend : DEFAULT_SETTINGS.autoSend,
    includeThinking: data.includeThinking !== undefined ? data.includeThinking : DEFAULT_SETTINGS.includeThinking,
    history: data.history || []
  };
}

// Append an item to history
async function addToHistory(item) {
  try {
    const { history } = await getSettings();
    const updatedHistory = [item, ...history].slice(0, 40);
    await chrome.storage.local.set({ history: updatedHistory });
  } catch (err) {
    console.error('[DeepSeek Bridge] Failed to save history:', err);
  }
}

// Perform fetch with automatic slash-retry
async function fetchWithRetry(url, options) {
  try {
    const response = await fetch(url, options);
    if (response.status === 500 || response.status === 404 || response.status === 301) {
      const alternateUrl = url.endsWith('/') ? url.slice(0, -1) : url + '/';
      console.warn(`[DeepSeek Bridge] Got status ${response.status} from ${url}, retrying with ${alternateUrl}`);
      try {
        const altResponse = await fetch(alternateUrl, options);
        if (altResponse.ok) {
          return { response: altResponse, usedUrl: alternateUrl };
        }
      } catch (altErr) {
        // Fall back to original
      }
    }
    return { response, usedUrl: url };
  } catch (err) {
    const alternateUrl = url.endsWith('/') ? url.slice(0, -1) : url + '/';
    try {
      const altResponse = await fetch(alternateUrl, options);
      return { response: altResponse, usedUrl: alternateUrl };
    } catch (e) {
      throw err;
    }
  }
}

// Helper to get base API URL
function getBaseUrl(serverUrl) {
  let cleaned = (serverUrl || DEFAULT_SETTINGS.serverUrl).trim();
  return cleaned.replace(/\/chat\/?$/, '');
}

// Check if a session exists in the backend DB
async function checkSessionInBackend(sessionId) {
  const settings = await getSettings();
  const baseUrl = getBaseUrl(settings.serverUrl);
  const targetUrl = `${baseUrl}/chat/sessions/${encodeURIComponent(sessionId)}/`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 6000);

    const { response } = await fetchWithRetry(targetUrl, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (response.ok) {
      const data = await response.json();
      return { success: true, ...data };
    }

    return { success: false, exists: false, error: `HTTP ${response.status}` };
  } catch (err) {
    console.error('[DeepSeek Bridge] checkSessionInBackend error:', err);
    return { success: false, exists: false, error: err.message };
  }
}

// Create or update a session in the backend DB
async function createSessionInBackend(sessionData) {
  const settings = await getSettings();
  const baseUrl = getBaseUrl(settings.serverUrl);
  const targetUrl = `${baseUrl}/chat/sessions/`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    const { response } = await fetchWithRetry(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(sessionData),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (response.ok) {
      const data = await response.json();
      return { success: true, ...data };
    }

    const text = await response.text();
    return { success: false, error: `HTTP ${response.status}: ${text}` };
  } catch (err) {
    console.error('[DeepSeek Bridge] createSessionInBackend error:', err);
    return { success: false, error: err.message };
  }
}

// Update session mode in backend
async function setSessionModeInBackend(sessionId, mode) {
  const settings = await getSettings();
  const baseUrl = getBaseUrl(settings.serverUrl);
  const targetUrl = `${baseUrl}/chat/sessions/${encodeURIComponent(sessionId)}/mode/`;

  try {
    const { response } = await fetchWithRetry(targetUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode })
    });
    if (response.ok) {
      return await response.json();
    }
    return { success: false, error: `HTTP ${response.status}` };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

// Forward chat message payload to localhost
async function sendChatToServer(chatData) {
  const settings = await getSettings();
  let targetUrl = (settings.serverUrl || DEFAULT_SETTINGS.serverUrl).trim();

  const payload = {
    message: chatData.message || '',
    thinking: settings.includeThinking ? (chatData.thinking || null) : null,
    role: chatData.role || 'assistant',
    model: chatData.model || 'deepseek',
    timestamp: chatData.timestamp || new Date().toISOString(),
    source: 'deepseek-web',
    url: chatData.url || '',
    session_id: chatData.sessionId || chatData.session_id || null,
    manual: Boolean(chatData.manual)
  };

  const historyEntry = {
    id: 'msg_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7),
    timestamp: payload.timestamp,
    messagePreview: payload.message.substring(0, 120),
    serverUrl: targetUrl,
    status: 'pending',
    statusCode: null,
    error: null,
    manual: payload.manual
  };

  try {
    console.log('[DeepSeek Bridge] Sending POST to:', targetUrl);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    const { response, usedUrl } = await fetchWithRetry(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*'
      },
      body: JSON.stringify(payload),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    let responseData = null;
    try {
      const text = await response.text();
      try {
        responseData = JSON.parse(text);
      } catch (e) {
        responseData = text;
      }
    } catch (e) {
      responseData = null;
    }

    historyEntry.serverUrl = usedUrl;
    historyEntry.status = response.ok ? 'success' : 'failed';
    historyEntry.statusCode = response.status;
    if (!response.ok) {
      historyEntry.error = `HTTP ${response.status} ${response.statusText}`;
    }

    await addToHistory(historyEntry);

    return {
      success: response.ok,
      status: response.status,
      statusText: response.statusText,
      data: responseData,
      targetUrl: usedUrl
    };
  } catch (error) {
    const errorMsg = error.name === 'AbortError' ? 'Connection timed out (10s)' : (error.message || 'Network error');
    console.error('[DeepSeek Bridge] Fetch failed:', error);

    historyEntry.status = 'error';
    historyEntry.error = errorMsg;
    await addToHistory(historyEntry);

    return {
      success: false,
      error: errorMsg,
      targetUrl
    };
  }
}

// Test server connection
async function testConnection(customUrl) {
  const settings = await getSettings();
  let targetUrl = (customUrl || settings.serverUrl || DEFAULT_SETTINGS.serverUrl).trim();

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    const testPayload = {
      message: 'DeepSeek Bridge connection test',
      ping: true,
      timestamp: new Date().toISOString(),
      source: 'deepseek-bridge-test'
    };

    const { response, usedUrl } = await fetchWithRetry(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(testPayload),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    return {
      connected: response.ok,
      status: response.status,
      statusText: response.statusText,
      url: usedUrl
    };
  } catch (err) {
    return {
      connected: false,
      error: err.name === 'AbortError' ? 'Timeout (5s)' : (err.message || 'Cannot reach server'),
      url: targetUrl
    };
  }
}

// Listen for messages from content scripts or popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'SEND_CHAT') {
    sendChatToServer(request.data).then(sendResponse);
    return true;
  }

  if (request.action === 'CHECK_SESSION') {
    checkSessionInBackend(request.sessionId).then(sendResponse);
    return true;
  }

  if (request.action === 'CREATE_SESSION') {
    createSessionInBackend(request.sessionData).then(sendResponse);
    return true;
  }

  if (request.action === 'SET_SESSION_MODE') {
    setSessionModeInBackend(request.sessionId, request.mode).then(sendResponse);
    return true;
  }

  if (request.action === 'TEST_CONNECTION') {
    testConnection(request.url).then(sendResponse);
    return true;
  }

  if (request.action === 'GET_SETTINGS') {
    getSettings().then(sendResponse);
    return true;
  }

  if (request.action === 'SAVE_SETTINGS') {
    chrome.storage.local.set(request.settings).then(() => {
      sendResponse({ success: true });
    });
    return true;
  }

  if (request.action === 'CLEAR_HISTORY') {
    chrome.storage.local.set({ history: [] }).then(() => {
      sendResponse({ success: true });
    });
    return true;
  }
});
