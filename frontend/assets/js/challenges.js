/**
 * EcoQuest — Challenges Module
 * Challenge cards, category filter, completion flow, and streak tracker.
 */
import { api, currentUser, removeSkeleton, toast, _escapeHtml } from './app.js';

let allChallenges   = [];
let activeFilter    = 'all';
let completedToday  = new Set(JSON.parse(localStorage.getItem('eq_completed') || '[]'));

export function initChallenges() {
  window.addEventListener('routechange', ({ detail }) => {
    if (detail.hash === '#challenges') loadChallenges();
  });

  // Filter tabs
  document.querySelectorAll('#view-challenges .filter-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#view-challenges .filter-tab').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      activeFilter = btn.dataset.filter || 'all';
      renderChallenges();
    });
  });

  if (location.hash === '#challenges') loadChallenges();
}

async function loadChallenges() {
  const grid = document.getElementById('challenges-list');
  if (!grid) return;

  // Show skeletons
  grid.innerHTML = '<div class="challenge-card skeleton" aria-hidden="true"></div>'.repeat(6);

  try {
    allChallenges = await api.get('/challenges');
    _updateStreakBanner();
    renderChallenges();
  } catch (err) {
    grid.innerHTML = `<p class="empty-state__desc">⚠️ Could not load challenges: ${_escapeHtml(err.message)}</p>`;
  }
}

function renderChallenges() {
  const grid = document.getElementById('challenges-list');
  if (!grid) return;
  removeSkeleton(grid);

  const filtered = activeFilter === 'all'
    ? allChallenges
    : allChallenges.filter(c => c.category === activeFilter);

  if (!filtered.length) {
    grid.innerHTML = '<p class="empty-state__desc">No challenges in this category right now.</p>';
    return;
  }

  grid.innerHTML = filtered.map(c => _challengeCard(c)).join('');

  // Attach complete buttons
  grid.querySelectorAll('.complete-btn').forEach(btn => {
    btn.addEventListener('click', () => completeChallenge(btn.dataset.id, btn));
  });
}

function _challengeCard(c) {
  const done = completedToday.has(c.id);
  const diffTag = `<span class="challenge-tag tag--${c.difficulty}">${_capitalize(c.difficulty)}</span>`;
  const catTag  = `<span class="challenge-tag tag--cat">${_categoryEmoji(c.category)} ${_capitalize(c.category)}</span>`;
  return `
    <article class="challenge-card ${done ? 'challenge-card--completed' : ''}"
             aria-label="${_escapeHtml(c.title)} challenge">
      <div class="challenge-card__header">
        <h3 class="challenge-card__title">${_escapeHtml(c.title)}</h3>
        ${done ? '<span aria-label="Completed">✅</span>' : ''}
      </div>
      <p class="challenge-card__desc">${_escapeHtml(c.description)}</p>
      <div class="challenge-card__meta">${diffTag}${catTag}</div>
      <div class="challenge-card__stats">
        <span class="challenge-stat" aria-label="${c.points} points">
          🏅 <strong>${c.points} pts</strong>
        </span>
        <span class="challenge-stat" aria-label="${c.co2_savings_kg} kg CO2 savings">
          💚 <strong>${c.co2_savings_kg} kg</strong> CO₂
        </span>
        <span class="challenge-stat" aria-label="Frequency: ${c.frequency}">
          🔄 ${_capitalize(c.frequency)}
        </span>
      </div>
      <div class="challenge-card__footer">
        <button
          class="btn ${done ? 'btn--ghost' : 'btn--primary'} complete-btn"
          data-id="${c.id}"
          ${done ? 'disabled aria-label="Already completed"' : `aria-label="Complete ${_escapeHtml(c.title)} challenge"`}
          style="width:100%"
        >
          ${done ? '✅ Completed Today' : '⚡ Mark Complete'}
        </button>
      </div>
    </article>
  `;
}

async function completeChallenge(challengeId, btn) {
  if (!currentUser.profile) {
    toast.warning('Complete the Carbon Quiz first to start earning points!');
    window.location.hash = '#quiz';
    return;
  }

  btn.disabled = true;
  btn.classList.add('loading');

  try {
    const result = await api.post(`/challenges/${challengeId}/complete`, {
      user_id: currentUser.id,
    });

    // Update local state
    completedToday.add(challengeId);
    localStorage.setItem('eq_completed', JSON.stringify([...completedToday]));

    // Update week counter
    const wk = parseInt(localStorage.getItem('ecoquest_week_challenges') || '0') + 1;
    localStorage.setItem('ecoquest_week_challenges', wk);

    // Update profile cache
    if (currentUser.profile) {
      currentUser.profile.total_points  = result.new_total_points;
      currentUser.profile.current_streak = result.new_streak;
      currentUser.profile.total_co2_saved_kg = (currentUser.profile.total_co2_saved_kg || 0) + result.co2_saved_kg;
    }

    let msg = `+${result.points_awarded} pts! Saved ${result.co2_saved_kg} kg CO₂ 🎉`;
    if (result.streak_bonus > 0) msg += ` 🔥 Streak bonus: +${result.streak_bonus} pts!`;
    if (result.milestone_reached) msg += ` 🏆 7-day milestone reached!`;
    toast.success(msg);

    _updateStreakBanner(result.new_streak);
    renderChallenges();
    window.dispatchEvent(new CustomEvent('pointsUpdated', { detail: result }));

  } catch (err) {
    if (err.message.includes('already completed')) {
      completedToday.add(challengeId);
      toast.warning('Already completed within this challenge window!');
      renderChallenges();
    } else {
      toast.error('Could not complete challenge: ' + err.message);
      btn.disabled = false;
    }
  } finally {
    btn.classList.remove('loading');
  }
}

function _updateStreakBanner(streak) {
  const s = streak ?? currentUser.profile?.current_streak ?? 0;
  const countEl = document.getElementById('streak-count');
  const msgEl   = document.getElementById('streak-msg');
  if (countEl) countEl.textContent = s;
  if (msgEl) {
    msgEl.textContent = s === 0
      ? 'Complete a challenge today to start your streak!'
      : s >= 7
        ? '🏆 Legendary streak! Keep it going!'
        : `Keep going — ${7 - (s % 7)} days to your next bonus!`;
  }
}

function _capitalize(s) { return s ? s[0].toUpperCase() + s.slice(1) : ''; }
function _categoryEmoji(cat) {
  return { transport:'🚗', food:'🥗', energy:'⚡', shopping:'🛍️', lifestyle:'🌿' }[cat] || '🌱';
}
