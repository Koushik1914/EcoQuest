/**
 * EcoQuest — Eco Clubs Module
 * Club browser and join flow.
 */
import { api, currentUser, toast, _escapeHtml } from './app.js';

let initialized = false;

export function initClubs() {
  if (initialized) return;
  initialized = true;
  loadClubs();
}

async function loadClubs() {
  const grid = document.getElementById('clubs-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="club-card skeleton" aria-hidden="true"></div>'.repeat(6);

  try {
    const data = await api.get('/clubs');
    grid.innerHTML = '';
    if (!data.clubs.length) {
      grid.innerHTML = '<p class="empty-state__desc">No clubs yet. Coming soon!</p>';
      return;
    }
    data.clubs.forEach(club => {
      grid.insertAdjacentHTML('beforeend', _clubCard(club));
    });
    grid.querySelectorAll('.join-btn').forEach(btn => {
      btn.addEventListener('click', () => joinClub(btn.dataset.clubId, btn));
    });
  } catch (err) {
    grid.innerHTML = `<p class="empty-state__desc">⚠️ ${_escapeHtml(err.message)}</p>`;
  }
}

function _clubCard(club) {
  const typeEmoji = { college: '🎓', office: '💼', city: '🏙️' }[club.club_type] || '🌱';
  const alreadyJoined = currentUser.profile?.club_id === club.id;
  return `
    <article class="club-card" aria-label="${_escapeHtml(club.name)} club">
      <div class="club-card__icon" aria-hidden="true">${typeEmoji}</div>
      <h3 class="club-card__name">${_escapeHtml(club.name)}</h3>
      <div class="club-card__type">${_capitalize(club.club_type)}</div>
      <p class="club-card__desc">${_escapeHtml(club.description)}</p>
      <div class="club-card__stats">
        <div class="club-stat">
          <span class="club-stat__val">${club.member_count.toLocaleString()}</span>
          <span class="club-stat__label">Members</span>
        </div>
        <div class="club-stat">
          <span class="club-stat__val">${club.total_co2_saved.toFixed(1)} kg</span>
          <span class="club-stat__label">CO₂ Saved</span>
        </div>
        <div class="club-stat">
          <span class="club-stat__val">${club.national_rank ? `#${club.national_rank}` : '—'}</span>
          <span class="club-stat__label">National Rank</span>
        </div>
      </div>
      <button
        class="btn ${alreadyJoined ? 'btn--ghost' : 'btn--primary'} join-btn"
        data-club-id="${club.id}"
        ${alreadyJoined ? 'disabled aria-label="Already a member"' : `aria-label="Join ${_escapeHtml(club.name)}"`}
        style="width:100%;margin-top:auto"
      >
        ${alreadyJoined ? '✅ Member' : '+ Join Club'}
      </button>
    </article>
  `;
}

async function joinClub(clubId, btn) {
  if (!currentUser.profile) {
    toast.warning('Complete the quiz first!');
    return;
  }
  btn.disabled = true;
  btn.classList.add('loading');
  try {
    const result = await api.post(`/clubs/${clubId}/join`, { user_id: currentUser.id });
    if (currentUser.profile) currentUser.profile.club_id = clubId;
    localStorage.setItem('ecoquest_profile', JSON.stringify(currentUser.profile));
    toast.success(`Joined the club! Welcome to the team 🌱 (${result.new_member_count} members)`);
    btn.textContent = '✅ Member';
    btn.classList.replace('btn--primary','btn--ghost');
  } catch (err) {
    toast.error('Could not join: ' + err.message);
    btn.disabled = false;
  } finally {
    btn.classList.remove('loading');
  }
}

function _capitalize(s) { return s ? s[0].toUpperCase() + s.slice(1) : ''; }
