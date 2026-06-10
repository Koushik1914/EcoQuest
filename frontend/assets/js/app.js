/**
 * EcoQuest — Core Application Module
 * Client-side router, auth state, API client, toast system, and module orchestration.
 * ES module pattern — no bundler required.
 */

// ── Configuration ─────────────────────────────────────────────────────────────
const BACKEND_URL = window.__ECOQUEST_API__ || 'BACKEND_URL_PLACEHOLDER';
const USER_KEY    = 'ecoquest_user_id';
const PROFILE_KEY = 'ecoquest_profile';

// ── User state (persisted to localStorage) ────────────────────────────────────
export let currentUser = {
  id: localStorage.getItem(USER_KEY) || _generateUserId(),
  profile: _loadProfile(),
};

function _generateUserId() {
  const id = 'user_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  localStorage.setItem(USER_KEY, id);
  return id;
}

function _loadProfile() {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function saveProfile(profile) {
  currentUser.profile = profile;
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  _refreshUserBadge();
}

function _refreshUserBadge() {
  const p = currentUser.profile;
  if (!p) return;
  const avatarEl  = document.getElementById('user-avatar');
  const pointsEl  = document.getElementById('user-points');
  const streakEl  = document.getElementById('streak-badge');
  if (avatarEl)  avatarEl.textContent  = p.avatar_emoji || '🌱';
  if (pointsEl)  pointsEl.textContent  = `${(p.total_points || 0).toLocaleString()} pts`;
  if (streakEl)  streakEl.textContent  = `🔥 ${p.current_streak || 0}`;
}

// ── API Client ────────────────────────────────────────────────────────────────
export const api = {
  async get(path, params = {}) {
    const url = new URL(BACKEND_URL + path);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    });
    return _fetch(url.toString(), { method: 'GET' });
  },

  async post(path, body) {
    return _fetch(BACKEND_URL + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  },

  async streamPost(path, body, onChunk, onDone, onError) {
    try {
      const res = await fetch(BACKEND_URL + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).replace(/\\n/g, '\n');
          if (data === '[DONE]') { onDone(); return; }
          if (data.startsWith('[ERROR]')) { onError(data); return; }
          onChunk(data);
        }
      }
      onDone();
    } catch (err) {
      onError(err.message);
    }
  },
};

async function _fetch(url, options, retries = 2) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, options);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      if (attempt === retries) throw err;
      await new Promise(r => setTimeout(r, 300 * (attempt + 1)));
    }
  }
}

// ── Toast Notification System ─────────────────────────────────────────────────
export const toast = {
  success(msg) { _showToast(msg, 'success', '✅'); },
  error(msg)   { _showToast(msg, 'error',   '❌'); },
  warning(msg) { _showToast(msg, 'warning', '⚠️'); },
  info(msg)    { _showToast(msg, 'info',    'ℹ️'); },
};

function _showToast(message, type, icon) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  el.setAttribute('role', 'alert');
  el.setAttribute('aria-live', 'assertive');
  el.innerHTML = `<span aria-hidden="true">${icon}</span> ${_escapeHtml(message)}`;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

export function _escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Client-side Router ────────────────────────────────────────────────────────
const ROUTES = {
  '#dashboard':  'view-dashboard',
  '#quiz':       'view-quiz',
  '#challenges': 'view-challenges',
  '#chat':       'view-chat',
};
const NAV_MAP = {
  '#dashboard':  'nav-dashboard',
  '#quiz':       'nav-quiz',
  '#challenges': 'nav-challenges',
  '#chat':       'nav-chat',
};

function navigate(hash) {
  const viewId = ROUTES[hash] || ROUTES['#dashboard'];
  Object.values(ROUTES).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.hidden = (id !== viewId);
  });
  Object.entries(NAV_MAP).forEach(([h, navId]) => {
    const el = document.getElementById(navId);
    if (el) {
      el.setAttribute('aria-current', h === hash ? 'page' : 'false');
    }
  });
  document.title = `EcoQuest — ${_titleForHash(hash)}`;
  window.dispatchEvent(new CustomEvent('routechange', { detail: { hash } }));
}

function _titleForHash(hash) {
  const titles = {
    '#dashboard':  'Dashboard',
    '#quiz':       'Carbon Quiz',
    '#challenges': 'Challenges',
    '#chat':       'EcoBuddy AI',
  };
  return titles[hash] || 'EcoQuest';
}

// ── Mobile nav toggle ─────────────────────────────────────────────────────────
function _initMobileMenu() {
  const btn = document.getElementById('menu-btn');
  const nav = document.getElementById('mobile-nav');
  if (!btn || !nav) return;
  btn.addEventListener('click', () => {
    const expanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!expanded));
    nav.hidden = expanded;
  });
}

// ── Skeleton removal helpers ──────────────────────────────────────────────────
export function removeSkeleton(container) {
  container.querySelectorAll('.skeleton').forEach(el => el.remove());
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  // Routing
  window.addEventListener('hashchange', () => navigate(location.hash));
  navigate(location.hash || '#dashboard');

  // Mobile nav
  _initMobileMenu();

  // Refresh user badge
  _refreshUserBadge();

  // Lazy-load view modules
  const { initDashboard } = await import('./dashboard.js');
  const { initQuiz }      = await import('./quiz.js');
  const { initChallenges }= await import('./challenges.js');
  const { initChat }      = await import('./chat.js');

  initDashboard();
  initQuiz();
  initChallenges();
  initChat();

  // Redirect to quiz if no profile yet
  if (!currentUser.profile && location.hash !== '#quiz') {
    navigate('#quiz');
    toast.info('Welcome! Take the quiz to set up your profile.');
  }
}

document.addEventListener('DOMContentLoaded', init);
