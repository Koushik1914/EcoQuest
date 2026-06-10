/**
 * EcoQuest — Leaderboard Module
 * Individual and club leaderboards with sub-tabs and current-user sticky row.
 */
import { api, currentUser, toast, _escapeHtml } from './app.js';

let initialized = false;

export function initLeaderboard() {
  if (initialized) return;
  initialized = true;
  _initSubTabs();
  loadIndividualLeaderboard();
}

function _initSubTabs() {
  const tabs = document.querySelectorAll('.sub-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected','false'); });
      tab.classList.add('active'); tab.setAttribute('aria-selected','true');
      const panelId = tab.getAttribute('aria-controls');
      document.querySelectorAll('[role="tabpanel"]').forEach(p => {
        if (p.closest('#panel-leaderboard')) p.hidden = true;
      });
      const panel = document.getElementById(panelId);
      if (panel) panel.hidden = false;

      if (panelId === 'lb-panel-clubs') loadClubLeaderboard();
    });
  });
}

async function loadIndividualLeaderboard() {
  const tbody = document.getElementById('lb-individual-body');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7">Loading…</td></tr>';

  try {
    const data = await api.get('/leaderboard/individual', { user_id: currentUser.id });
    if (!data.entries.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#6b7280">No eligible users yet. Complete the quiz and 3 challenges to appear here.</td></tr>';
      return;
    }
    tbody.innerHTML = data.entries.map(e => _individualRow(e)).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7">⚠️ ${_escapeHtml(err.message)}</td></tr>`;
  }
}

function _individualRow(entry) {
  const medal = entry.rank === 1 ? '🥇' : entry.rank === 2 ? '🥈' : entry.rank === 3 ? '🥉' : `#${entry.rank}`;
  const highlight = entry.is_current_user ? 'current-user' : '';
  const tier = _tierLabel(entry.rank_tier);
  return `
    <tr class="${highlight}" ${entry.is_current_user ? 'aria-label="Your row"' : ''}>
      <td><span class="rank-medal" aria-label="Rank ${entry.rank}">${medal}</span></td>
      <td>
        <span aria-hidden="true">${_escapeHtml(entry.avatar_emoji || '🌱')}</span>
        ${_escapeHtml(entry.display_name)}
        ${entry.is_current_user ? '<strong>(You)</strong>' : ''}
      </td>
      <td>${_escapeHtml(entry.city)}</td>
      <td><span class="tier-badge">${tier}</span></td>
      <td>${entry.improvement_pct.toFixed(1)}%</td>
      <td>${entry.total_points.toLocaleString()}</td>
      <td>${entry.rank_score.toFixed(1)}</td>
    </tr>
  `;
}

async function loadClubLeaderboard() {
  const tbody = document.getElementById('lb-clubs-body');
  if (!tbody || tbody.dataset.loaded) return;
  tbody.innerHTML = '<tr><td colspan="7">Loading…</td></tr>';

  try {
    const data = await api.get('/leaderboard/clubs');
    if (!data.entries.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#6b7280">No clubs yet. Create one in the Eco Clubs tab!</td></tr>';
      return;
    }
    tbody.innerHTML = data.entries.map(c => _clubRow(c)).join('');
    tbody.dataset.loaded = 'true';
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7">⚠️ ${_escapeHtml(err.message)}</td></tr>`;
  }
}

function _clubRow(entry) {
  const medal = entry.rank === 1 ? '🥇' : entry.rank === 2 ? '🥈' : entry.rank === 3 ? '🥉' : `#${entry.rank}`;
  return `
    <tr>
      <td><span class="rank-medal">${medal}</span></td>
      <td>${_escapeHtml(entry.name)}</td>
      <td>${_capitalize(entry.club_type)}</td>
      <td>${entry.member_count.toLocaleString()}</td>
      <td>${entry.total_co2_saved.toFixed(1)} kg</td>
      <td>${entry.total_action_points.toLocaleString()}</td>
      <td>${entry.score.toFixed(1)}</td>
    </tr>
  `;
}

function _tierLabel(tier) {
  return {
    seedling:         '🌱 Seedling',
    eco_explorer:     '🍃 Eco Explorer',
    climate_champion: '🌍 Champion',
    planet_protector: '🏆 Protector',
  }[tier] || '🌱';
}
function _capitalize(s) { return s ? s[0].toUpperCase() + s.slice(1) : ''; }
