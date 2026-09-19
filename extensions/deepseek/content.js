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

  // 1. Get current DeepSeek session ID
  function getCurrentSessionId() {
    const urlMatch = window.location.pathname.match(/\/a\/chat\/s\/([a-zA-Z0-9_\-]+)/);
    if (urlMatch && urlMatch[1]) {
      return urlMatch[1];
    }
    if (!window.__DEEPSEEK_SESSION_ID__) {
      window.__DEEPSEEK_SESSION_ID__ = 'session_' + Math.random().toString(36).substring(2, 11);
    }
    return window.__DEEPSEEK_SESSION_ID__;
  }

  // 2. Load initial settings
  chrome.runtime.sendMessage({ action: 'GET_SETTINGS' }, (res) => {
    if (res) {
      appSettings = { ...appSettings, ...res };
      updateAllToggleUI();
      console.log('[DeepSeek Bridge] Settings loaded:', appSettings);
    }
  });

  // 3. Listen for settings changes across extension
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.serverUrl) appSettings.serverUrl = changes.serverUrl.newValue;
    if (changes.autoSend !== undefined) {
      appSettings.autoSend = changes.autoSend.newValue;
      updateAllToggleUI();
    }
    if (changes.includeThinking !== undefined) appSettings.includeThinking = changes.includeThinking.newValue;
  });

  function setLocalAutoSend(val) {
    appSettings.autoSend = Boolean(val);
    chrome.storage.local.set({ autoSend: appSettings.autoSend });
    updateAllToggleUI();
  }

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

  // 4. Attach System Prompt as Markdown file to DeepSeek chat
  function attachMarkdownFileToChat(filename, markdownContent) {
    if (!markdownContent) return;

    // Attach via DeepSeek's file input
    const fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
      try {
        const file = new File([markdownContent], filename, { type: 'text/markdown' });
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        fileInput.files = dataTransfer.files;
        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
        fileInput.dispatchEvent(new Event('input', { bubbles: true }));
        console.log('[DeepSeek Bridge] Successfully attached file via fileInput:', filename);
      } catch (err) {
        console.error('[DeepSeek Bridge] Failed to attach file to fileInput:', err);
      }
    }

    // Populate textarea with instruction if empty
    const textarea = document.querySelector('textarea, [contenteditable="true"]');
    if (textarea) {
      const instructionText = `فایل پیوست‌شده \`${filename}\` حاوی دستورالعمل سیستم (System Prompt) و محیط پروژه است. لطفاً آن را به عنوان راهنمای قوانین پروژه و چارچوب کار مدنظر قرار بده.`;
      if (textarea.tagName === 'TEXTAREA') {
        if (!textarea.value.trim()) {
          textarea.value = instructionText;
          textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }
      } else {
        if (!textarea.innerText.trim()) {
          textarea.innerText = instructionText;
          textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }
      }
    }
  }

  // 5. Open Project Setup Modal Dialog for new sessions
  function openProjectSetupModal(sessionId, onConfirmed) {
    let overlay = document.getElementById('ds-bridge-modal-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'ds-bridge-modal-overlay';
      overlay.className = 'ds-bridge-modal-overlay';

      overlay.innerHTML = `
        <div class="ds-bridge-modal-box">
          <div class="ds-bridge-modal-header">
            <div class="ds-bridge-modal-title">
              <span>📁 تنظیم پروژه محلی برای این گفتگو</span>
            </div>
            <button class="ds-bridge-modal-close" id="ds-modal-close-btn">&times;</button>
          </div>
          <div class="ds-bridge-modal-body">
            <p class="ds-bridge-modal-desc">
              این گفتگو هنوز در دیتابیس ثبت نشده است. لطفاً پوشه پروژه را انتخاب کنید تا سیستم پرامپت اختصاصی تولید و به عنوان فایل <code>.md</code> به چت ضمیمه شود.
            </p>

            <input type="file" webkitdirectory directory id="ds-folder-native-picker" style="display:none;">

            <button type="button" class="ds-bridge-picker-btn" id="ds-folder-select-btn">
              <span>📂 انتخاب پوشه پروژه از کامپیوتر</span>
            </button>

            <div class="ds-bridge-form-group">
              <label class="ds-bridge-form-label">مسیر محلی پروژه (Project Path):</label>
              <input type="text" class="ds-bridge-form-input" id="ds-modal-project-path" placeholder="مثال: C:\\Users\\3ircle\\Documents\\projects\\my-app">
            </div>

            <div class="ds-bridge-form-group">
              <label class="ds-bridge-form-label">نام پروژه (اختیاری):</label>
              <input type="text" class="ds-bridge-form-input" id="ds-modal-project-name" placeholder="نام پروژه">
            </div>
          </div>
          <div class="ds-bridge-modal-footer">
            <button type="button" class="ds-bridge-modal-btn-cancel" id="ds-modal-cancel-btn">انصراف</button>
            <button type="button" class="ds-bridge-modal-btn-confirm" id="ds-modal-confirm-btn">
              <span>🚀 تایید و ارسال سیستم پرامپت به چت</span>
            </button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);

      const closeBtn = document.getElementById('ds-modal-close-btn');
      const cancelBtn = document.getElementById('ds-modal-cancel-btn');
      const confirmBtn = document.getElementById('ds-modal-confirm-btn');
      const folderBtn = document.getElementById('ds-folder-select-btn');
      const folderPicker = document.getElementById('ds-folder-native-picker');
      const pathInput = document.getElementById('ds-modal-project-path');
      const nameInput = document.getElementById('ds-modal-project-name');

      function closeModal() {
        overlay.classList.remove('open');
      }

      closeBtn.addEventListener('click', closeModal);
      cancelBtn.addEventListener('click', closeModal);

      folderBtn.addEventListener('click', () => {
        folderPicker.click();
      });

      folderPicker.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files && files.length > 0) {
          const firstPath = files[0].webkitRelativePath || '';
          const folderName = firstPath.split('/')[0] || 'project';
          nameInput.value = folderName;
          pathInput.value = `C:\\Users\\3ircle\\Documents\\projects\\${folderName}`;
          showToast(`پوشه "${folderName}" انتخاب شد`);
        }
      });

      confirmBtn.addEventListener('click', () => {
        const projectPath = pathInput.value.trim();
        const projectName = nameInput.value.trim() || (projectPath ? projectPath.split(/[\\/]/).filter(Boolean).pop() : 'project');

        if (!projectPath) {
          showToast('لطفاً مسیر پروژه را مشخص یا انتخاب کنید', 'error');
          pathInput.focus();
          return;
        }

        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<span>⏳ در حال تولید سیستم پرامپت...</span>';

        const sessionPayload = {
          session_id: sessionId,
          project_path: projectPath,
          project_name: projectName
        };

        chrome.runtime.sendMessage({ action: 'CREATE_SESSION', sessionData: sessionPayload }, (res) => {
          confirmBtn.disabled = false;
          confirmBtn.innerHTML = '<span>🚀 تایید و ارسال سیستم پرامپت به چت</span>';

          if (res && res.success) {
            closeModal();
            if (typeof onConfirmed === 'function') {
              onConfirmed(res);
            }
          } else {
            const err = (res && res.error) || 'خطا در ثبت سشن در سرور';
            showToast(`خطا: ${err}`, 'error');
          }
        });
      });
    }

    overlay.classList.add('open');
    const pathInput = document.getElementById('ds-modal-project-path');
    const nameInput = document.getElementById('ds-modal-project-name');
    if (pathInput) pathInput.value = '';
    if (nameInput) nameInput.value = '';
  }

  // 6. Handle Auto-Send toggle activation (Checks session existence first!)
  function handleTurnOnAutoSend() {
    const sessionId = getCurrentSessionId();
    console.log('[DeepSeek Bridge] Checking session in backend:', sessionId);

    const toggleBtn = document.getElementById('ds-bridge-auto-toggle');
    const textSpan = toggleBtn?.querySelector('.ds-bridge-toggle-text');
    if (textSpan) textSpan.textContent = 'بررسی سشن...';

    chrome.runtime.sendMessage({ action: 'CHECK_SESSION', sessionId }, (res) => {
      if (res && res.exists) {
        // Session already saved in DB! Do nothing ("که هیچی"), just enable auto-send
        console.log('[DeepSeek Bridge] Session already exists in DB:', res.session);
        setLocalAutoSend(true);
        const projectName = res.session?.project_name || 'ثبت‌شده';
        showToast(`✓ ارسال خودکار فعال شد (پروژه: ${projectName})`, 'success');
      } else {
        // Session is new / not in DB! Prompt user for project folder
        console.log('[DeepSeek Bridge] Session not found in DB. Opening project setup modal...');
        if (textSpan) textSpan.textContent = 'ارسال خودکار: خاموش';
        openProjectSetupModal(sessionId, (createdData) => {
          setLocalAutoSend(true);
          if (createdData && createdData.system_prompt) {
            const filename = createdData.filename || 'system_prompt.md';
            attachMarkdownFileToChat(filename, createdData.system_prompt);
          }
          showToast(`✓ سشن در دیتابیس ذخیره شد و فایل سیستم پرامپت به چت ضمیمه گردید!`, 'success', 5000);
        });
      }
    });
  }

  // 7. Send message payload to background service worker (which POSTs to localhost)
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
      session_id: getCurrentSessionId(),
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

  // 8. Stream intercept from inject.js (Network layer)
  window.addEventListener('message', (event) => {
    if (event.source !== window || !event.data) return;

    if (event.data.type === 'DEEPSEEK_BRIDGE_STREAM_COMPLETE') {
      const payload = event.data.payload;
      console.log('[DeepSeek Bridge] Network SSE stream completed.');
      if (payload && payload.message) {
        latestExtractedMessage = payload;
        if (appSettings.autoSend) {
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

  function isGeneratingActive() {
    const buttons = document.querySelectorAll('button, div[role="button"]');
    for (const b of buttons) {
      const aria = (b.getAttribute('aria-label') || '').toLowerCase();
      const txt = (b.textContent || '').toLowerCase();
      if (aria.includes('stop') || txt.includes('stop') || txt.includes('توقف') || txt.includes('停止')) {
        return true;
      }
      if (b.querySelector('svg rect')) {
        return true;
      }
    }

    if (document.querySelector('.ds-cursor, [class*="ds-cursor"], [class*="blinking-cursor"]')) {
      return true;
    }

    return false;
  }

  function isMessageFullyCompleted(container) {
    if (!container) return false;

    if (isGeneratingActive()) {
      return false;
    }

    const copyBtn = container.querySelector('[aria-label*="Copy"], [aria-label*="کپی"], [title*="Copy"], [title*="کپی"], svg[class*="copy"]');
    if (copyBtn) {
      return true;
    }

    const actionGroup = container.querySelector('[class*="action"], [class*="tool"], [class*="operate"], [class*="button-group"]');
    if (actionGroup && actionGroup.children.length >= 2) {
      return true;
    }

    return false;
  }

  function extractAssistantMessage(container) {
    if (!container) return null;

    const mdEl = container.matches('.ds-markdown, [class*="ds-markdown"], [class*="markdown"], [class*="prose"]')
      ? container
      : container.querySelector('.ds-markdown, [class*="ds-markdown"], [class*="markdown"], [class*="prose"]');

    let thinking = null;
    const thinkEl = container.querySelector('[class*="ds-think"], [class*="think"], details, [class*="reasoning"]');
    if (thinkEl) {
      thinking = thinkEl.innerText.trim();
    }

    let messageText = '';
    if (mdEl) {
      const clone = mdEl.cloneNode(true);
      const innerThink = clone.querySelector('[class*="ds-think"], [class*="think"], details, [class*="reasoning"]');
      if (innerThink) innerThink.remove();
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

    let searchEl = null;
    let deepThinkEl = null;

    const allCandidates = document.querySelectorAll('button, div[role="button"], span');
    for (const el of allCandidates) {
      const txt = (el.textContent || '').trim();
      if (!searchEl && (txt === 'Search' || txt.startsWith('Search'))) {
        searchEl = el.closest('button') || el.closest('[role="button"]') || el;
      }
      if (!deepThinkEl && (txt === 'DeepThink' || txt.startsWith('DeepThink'))) {
        deepThinkEl = el.closest('button') || el.closest('[role="button"]') || el;
      }
      if (searchEl && deepThinkEl) break;
    }

    let targetToolbar = null;
    let insertAfterPill = null;

    if (searchEl && deepThinkEl) {
      let curr = searchEl;
      while (curr && curr.parentElement && !curr.parentElement.contains(deepThinkEl)) {
        curr = curr.parentElement;
      }
      if (curr && curr.parentElement) {
        targetToolbar = curr.parentElement;
        insertAfterPill = curr;
      }
    } else if (searchEl || deepThinkEl) {
      const ref = searchEl || deepThinkEl;
      let curr = ref;
      while (curr && curr.parentElement && curr.parentElement !== document.body && curr.parentElement.children.length === 1) {
        curr = curr.parentElement;
      }
      if (curr && curr.parentElement) {
        targetToolbar = curr.parentElement;
        insertAfterPill = curr;
      }
    }

    if (!targetToolbar) {
      const textarea = document.querySelector('textarea, [contenteditable="true"]');
      if (textarea) {
        const form = textarea.closest('form') || textarea.parentElement?.parentElement;
        if (form) {
          const row = form.querySelector('[class*="tool"], [class*="footer"], [class*="action"], [class*="bottom"]');
          if (row) targetToolbar = row;
        }
      }
    }

    if (!targetToolbar) return;

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

      if (!appSettings.autoSend) {
        // Turning ON: check if session exists in DB or prompt for project folder!
        handleTurnOnAutoSend();
      } else {
        // Turning OFF
        setLocalAutoSend(false);
        showToast('ارسال خودکار پیام‌ها غیرفعال شد', 'info');
      }
    });

    if (insertAfterPill && insertAfterPill.nextSibling) {
      targetToolbar.insertBefore(toggleBtn, insertAfterPill.nextSibling);
    } else {
      targetToolbar.appendChild(toggleBtn);
    }

    console.log('[DeepSeek Bridge] Injected Auto-Send pill toggle in DeepSeek toolbar!');
  }

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
    injectInputToolbarToggle();
    injectMessageButtons();

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

    const isCompleted = isMessageFullyCompleted(latestContainer);

    if (currentLength !== lastObservedLength || isCurrentlyStreaming) {
      lastObservedLength = currentLength;
      clearTimeout(textStabilityTimer);

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
      if (e.target.checked) {
        handleTurnOnAutoSend();
      } else {
        setLocalAutoSend(false);
        showToast('ارسال خودکار پیام‌ها غیرفعال شد');
      }
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

  const checkInterval = setInterval(() => {
    injectInputToolbarToggle();
    injectMessageButtons();
  }, 1000);

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
