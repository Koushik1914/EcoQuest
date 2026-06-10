/**
 * EcoQuest — EcoBuddy AI Chat Module
 * SSE streaming chat with quick chips, history, and typing indicator.
 */
import { api, currentUser, toast, _escapeHtml } from './app.js';

let isStreaming = false;

export function initChat() {
  const form  = document.getElementById('chat-input-form');
  const input = document.getElementById('chat-input');
  const chips = document.querySelectorAll('.chip');

  if (!form) return;

  // Load chat history when view is shown
  window.addEventListener('routechange', ({ detail }) => {
    if (detail.hash === '#chat') loadHistory();
  });

  // Quick chips
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.dataset.prompt;
      if (prompt && input) {
        input.value = prompt;
        sendMessage(prompt);
      }
    });
  });

  // Form submit
  form.addEventListener('submit', e => {
    e.preventDefault();
    const msg = input?.value.trim();
    if (!msg) return;
    sendMessage(msg);
    if (input) input.value = '';
  });

  if (location.hash === '#chat') loadHistory();
}

async function loadHistory() {
  try {
    const data = await api.get('/chat/history', { user_id: currentUser.id });
    const msgs  = data.messages || [];
    if (!msgs.length) return;

    const container = document.getElementById('chat-messages');
    if (!container) return;
    // Keep the initial assistant greeting, append history
    msgs.slice(-10).forEach(msg => {
      _appendMessage(msg.content, msg.role === 'user' ? 'user' : 'assistant', false);
    });
    _scrollToBottom();
  } catch {
    // History not critical — fail silently
  }
}

async function sendMessage(text) {
  if (isStreaming) {
    toast.warning('EcoBuddy is still thinking…');
    return;
  }
  if (!text.trim()) return;

  _appendMessage(text, 'user');
  const typingEl = _appendTyping();
  isStreaming = true;

  const sendBtn = document.getElementById('chat-send-btn');
  if (sendBtn) sendBtn.disabled = true;

  let assistantEl = null;

  api.streamPost(
    '/chat',
    { user_id: currentUser.id, message: text },
    (chunk) => {
      // First chunk: replace typing indicator with real bubble
      if (!assistantEl) {
        typingEl?.remove();
        assistantEl = _appendMessage('', 'assistant');
      }
      const bubble = assistantEl.querySelector('.chat-message__bubble');
      if (bubble) {
        // Convert markdown-ish text to safe HTML
        bubble.innerHTML = _formatMarkdown(bubble.dataset.raw ? bubble.dataset.raw + chunk : chunk);
        bubble.dataset.raw = (bubble.dataset.raw || '') + chunk;
      }
      _scrollToBottom();
    },
    () => {
      // Done
      isStreaming = false;
      if (sendBtn) sendBtn.disabled = false;
      typingEl?.remove();
    },
    (err) => {
      isStreaming = false;
      if (sendBtn) sendBtn.disabled = false;
      typingEl?.remove();
      if (!assistantEl) {
        _appendMessage('Sorry, I had trouble responding. Please try again.', 'assistant');
      }
      toast.error('EcoBuddy: ' + err);
    }
  );
}

function _appendMessage(text, role, scroll = true) {
  const container = document.getElementById('chat-messages');
  if (!container) return null;

  const isUser = role === 'user';
  const el = document.createElement('div');
  el.className = `chat-message chat-message--${isUser ? 'user' : 'assistant'}`;
  el.innerHTML = `
    <div class="chat-message__avatar" aria-hidden="true">${isUser ? '👤' : '🌿'}</div>
    <div class="chat-message__bubble" aria-label="${isUser ? 'Your message' : 'EcoBuddy response'}">
      ${isUser ? _escapeHtml(text) : _formatMarkdown(text)}
    </div>
  `;
  container.appendChild(el);
  if (scroll) _scrollToBottom();
  return el;
}

function _appendTyping() {
  const container = document.getElementById('chat-messages');
  if (!container) return null;
  const el = document.createElement('div');
  el.className = 'chat-message chat-message--assistant chat-message--typing';
  el.setAttribute('aria-label', 'EcoBuddy is typing');
  el.innerHTML = `
    <div class="chat-message__avatar" aria-hidden="true">🌿</div>
    <div class="chat-message__bubble"></div>
  `;
  container.appendChild(el);
  _scrollToBottom();
  return el;
}

function _scrollToBottom() {
  const container = document.getElementById('chat-messages');
  if (container) container.scrollTop = container.scrollHeight;
}

function _formatMarkdown(text) {
  if (!text) return '';
  // Simple safe markdown: bold, bullets, line breaks
  return _escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^— (.+)$/gm, '<li>$1</li>')
    .replace(/^• (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]+?<\/li>)/g, '<ul>$1</ul>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^(?!<)/, '<p>')
    .replace(/(?!>)$/, '</p>');
}
