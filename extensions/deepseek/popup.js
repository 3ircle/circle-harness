// DeepSeek Bridge - Popup Controller

document.addEventListener('DOMContentLoaded', async () => {
  const serverUrlInput = document.getElementById('server-url');
  const saveUrlBtn = document.getElementById('save-url-btn');
  const autoSendToggle = document.getElementById('auto-send-toggle');
  const thinkingToggle = document.getElementById('thinking-toggle');
  const testConnectionBtn = document.getElementById('test-connection-btn');
  const openDeepseekBtn = document.getElementById('open-deepseek-btn');
  const clearHistoryBtn = document.getElementById('clear-history-btn');
  const historyContainer = document.getElementById('history-container');
  const historyEmpty = document.getElementById('history-empty');
  const statusIndicator = document.getElementById('status-indicator');
  const statusText = document.getElementById('status-text');

  // Load settings
  chrome.runtime.sendMessage({ action: 'GET_SETTINGS' }, (settings) => {
    if (settings) {
      serverUrlInput.value = settings.serverUrl || 'http://localhost:8000/chat/';
      autoSendToggle.checked = settings.autoSend !== false;
      thinkingToggle.checked = settings.includeThinking !== false;
      renderHistory(settings.history || []);
    }
  });

  // Check connection initially
  checkConnection();

  // Save Server URL
  saveUrlBtn.addEventListener('click', () => {
    const url = serverUrlInput.value.trim() || 'http://localhost:8000/chat/';
    chrome.runtime.sendMessage({
      action: 'SAVE_SETTINGS',
      settings: { serverUrl: url }
    }, () => {
      saveUrlBtn.textContent = '✓ ذخیره شد';
      setTimeout(() => {
        saveUrlBtn.textContent = 'ذخیره';
      }, 1500);
      checkConnection(url);
    });
  });

  serverUrlInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      saveUrlBtn.click();
    }
  });

  // Toggle Auto-Send
  autoSendToggle.addEventListener('change', (e) => {
    chrome.runtime.sendMessage({
      action: 'SAVE_SETTINGS',
      settings: { autoSend: e.target.checked }
    });
  });

  // Toggle Thinking
  thinkingToggle.addEventListener('change', (e) => {
    chrome.runtime.sendMessage({
      action: 'SAVE_SETTINGS',
      settings: { includeThinking: e.target.checked }
    });
  });

  // Test Connection
  testConnectionBtn.addEventListener('click', () => {
    checkConnection();
  });

  // Open DeepSeek tab
  openDeepseekBtn.addEventListener('click', () => {
    chrome.tabs.create({ url: 'https://chat.deepseek.com' });
  });

  // Clear History
  clearHistoryBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'CLEAR_HISTORY' }, () => {
      renderHistory([]);
    });
  });

  // Check server connection
  function checkConnection(overrideUrl) {
    statusIndicator.className = 'status-indicator';
    statusText.textContent = 'در حال بررسی...';
    testConnectionBtn.disabled = true;

    chrome.runtime.sendMessage({
      action: 'TEST_CONNECTION',
      url: overrideUrl || serverUrlInput.value.trim()
    }, (res) => {
      testConnectionBtn.disabled = false;
      if (res && res.connected) {
        statusIndicator.className = 'status-indicator online';
        statusText.textContent = `متصل (${res.status || 'OK'})`;
      } else {
        statusIndicator.className = 'status-indicator offline';
        statusText.textContent = 'قطع ارتباط';
      }
    });
  }

  // Render History Items
  function renderHistory(history) {
    historyContainer.innerHTML = '';

    if (!history || history.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'هیچ پیامی هنوز ارسال نشده است';
      historyContainer.appendChild(empty);
      return;
    }

    history.forEach(item => {
      const el = document.createElement('div');
      el.className = 'history-item';

      const dateStr = item.timestamp ? new Date(item.timestamp).toLocaleTimeString('fa-IR') : '--:--';
      const statusClass = item.status === 'success' ? 'success' : 'failed';
      const statusLabel = item.status === 'success' ? (item.statusCode || '200 OK') : (item.error || 'خطا');

      el.innerHTML = `
        <div class="history-item-header">
          <span class="history-badge ${statusClass}">${statusLabel}</span>
          <span class="history-time">${dateStr}</span>
        </div>
        <div class="history-msg" title="${escapeHtml(item.messagePreview || '')}">
          ${escapeHtml(item.messagePreview || '(پیام خالی)')}
        </div>
      `;

      historyContainer.appendChild(el);
    });
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
});
