/**
 * EcoQuest — Community Feed Module
 * Post feed CRUD, like toggle, image upload, filter, pagination.
 */
import { api, currentUser, toast, _escapeHtml } from './app.js';

let currentCategory = null;
let nextCursor      = null;
let isLoading       = false;

export function initCommunity() {
  _initPageTabs();
  _initCreatePost();
  loadPosts();

  // Feed filter
  document.querySelectorAll('#panel-feed .filter-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#panel-feed .filter-tab').forEach(b => {
        b.classList.remove('active'); b.setAttribute('aria-selected','false');
      });
      btn.classList.add('active'); btn.setAttribute('aria-selected','true');
      currentCategory = btn.dataset.filter === 'all' ? null : btn.dataset.filter;
      nextCursor = null;
      loadPosts(true);
    });
  });

  // Load more
  document.getElementById('load-more-btn')?.addEventListener('click', () => loadPosts());
}

function _initPageTabs() {
  const tabs   = document.querySelectorAll('.page-tab');
  const panels = document.querySelectorAll('.community-panel');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected','false'); });
      panels.forEach(p => p.hidden = true);
      tab.classList.add('active'); tab.setAttribute('aria-selected','true');
      const panelId = tab.getAttribute('aria-controls');
      const panel = document.getElementById(panelId);
      if (panel) panel.hidden = false;
      tab.id === 'tab-leaderboard' && _ensureLeaderboard();
      tab.id === 'tab-clubs'       && _ensureClubs();
    });
  });
}

async function loadPosts(reset = false) {
  if (isLoading) return;
  isLoading = true;
  const feed    = document.getElementById('post-feed');
  const loadBtn = document.getElementById('load-more-btn');
  if (!feed) return;

  if (reset) { feed.innerHTML = ''; nextCursor = null; }
  feed.setAttribute('aria-busy', 'true');

  if (!feed.querySelector('.post-card:not(.skeleton)')) {
    feed.innerHTML = '<article class="post-card skeleton" aria-hidden="true"></article>'.repeat(3);
  }

  try {
    const params = { limit: 20 };
    if (currentCategory) params.category = currentCategory;
    if (nextCursor)       params.cursor   = nextCursor;

    const data = await api.get('/posts', params);
    feed.querySelectorAll('.skeleton').forEach(s => s.remove());
    feed.setAttribute('aria-busy', 'false');

    if (!data.posts.length && !feed.querySelector('.post-card')) {
      feed.innerHTML = '<p class="empty-state__desc">No posts yet. Be the first to share an eco action! 🌿</p>';
      if (loadBtn) loadBtn.hidden = true;
      return;
    }

    data.posts.forEach(post => feed.insertAdjacentHTML('beforeend', _postCard(post)));
    nextCursor = data.next_cursor;
    if (loadBtn) loadBtn.hidden = !data.has_more;

    // Attach like listeners
    feed.querySelectorAll('.like-btn[data-post-id]').forEach(btn => {
      btn.addEventListener('click', () => handleLike(btn));
    });

  } catch (err) {
    feed.setAttribute('aria-busy', 'false');
    feed.querySelectorAll('.skeleton').forEach(s => s.remove());
    feed.insertAdjacentHTML('beforeend', `<p class="empty-state__desc">⚠️ ${_escapeHtml(err.message)}</p>`);
  } finally {
    isLoading = false;
  }
}

function _postCard(post) {
  const ago = _timeAgo(post.created_at);
  const img = post.image_url
    ? `<div class="post-card__image"><img src="${_escapeHtml(post.image_url)}" alt="Photo for post by ${_escapeHtml(post.display_name)}" loading="lazy"></div>`
    : '';
  const clubTag = post.club_tag
    ? `<span class="post-badge" aria-label="Club: ${_escapeHtml(post.club_tag)}">${_escapeHtml(post.club_tag)}</span>`
    : '';
  const verified = post.verified
    ? `<span class="post-badge" aria-label="Verified post">✅ Verified</span>`
    : '';

  return `
    <article class="post-card" aria-label="Post by ${_escapeHtml(post.display_name)}">
      <div class="post-card__header">
        <span class="post-avatar" aria-hidden="true">${_escapeHtml(post.avatar_emoji || '🌱')}</span>
        <div class="post-meta">
          <div class="post-author">${_escapeHtml(post.display_name)}</div>
          <div class="post-location">📍 ${_escapeHtml(post.city || '')} · <time datetime="${post.created_at}">${ago}</time></div>
        </div>
        ${clubTag}${verified}
      </div>
      <p class="post-card__body">${_escapeHtml(post.note)}</p>
      ${img}
      <div class="post-card__footer">
        <span class="post-co2" aria-label="${post.co2_saved_kg} kg CO2 saved">
          💚 Saved ${post.co2_saved_kg?.toFixed(1)} kg CO₂
        </span>
        <button class="like-btn ${post.likes?.includes(currentUser.id) ? 'liked' : ''}"
                data-post-id="${post.id}"
                aria-label="${post.likes_count} likes, click to like"
                aria-pressed="${post.likes?.includes(currentUser.id) ? 'true' : 'false'}">
          ❤️ ${post.likes_count || 0}
        </button>
      </div>
    </article>
  `;
}

async function handleLike(btn) {
  const postId = btn.dataset.postId;
  try {
    const result = await api.post(`/posts/${postId}/like?user_id=${currentUser.id}`, {});
    btn.innerHTML = `❤️ ${result.likes_count}`;
    btn.classList.toggle('liked', result.liked);
    btn.setAttribute('aria-pressed', String(result.liked));
    btn.setAttribute('aria-label', `${result.likes_count} likes`);
  } catch (err) {
    toast.error('Could not update like: ' + err.message);
  }
}

function _initCreatePost() {
  const createBtn  = document.getElementById('create-post-btn');
  const overlay    = document.getElementById('post-modal-overlay');
  const closeBtn   = document.getElementById('post-modal-close');
  const cancelBtn  = document.getElementById('post-cancel-btn');
  const form       = document.getElementById('post-form');
  const imageInput = document.getElementById('post-image');
  const preview    = document.getElementById('image-preview');
  const previewImg = document.getElementById('image-preview-img');
  const removeImg  = document.getElementById('remove-image');
  const noteArea   = document.getElementById('post-note');
  const noteChars  = document.getElementById('note-chars');

  if (!form) return;

  const openModal  = () => { if (overlay) overlay.hidden = false; form.reset(); if (preview) preview.hidden = true; };
  const closeModal = () => { if (overlay) overlay.hidden = true; };

  createBtn?.addEventListener('click', openModal);
  closeBtn?.addEventListener('click', closeModal);
  cancelBtn?.addEventListener('click', closeModal);
  overlay?.addEventListener('click', e => { if (e.target === overlay) closeModal(); });

  // Close on Escape
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !overlay?.hidden) closeModal(); });

  // Character counter
  noteArea?.addEventListener('input', () => {
    if (noteChars) noteChars.textContent = noteArea.value.length;
  });

  // Image preview
  imageInput?.addEventListener('change', () => {
    const file = imageInput.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Image must be under 5 MB.');
      imageInput.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = e => {
      if (previewImg) previewImg.src = e.target.result;
      if (preview)   preview.hidden = false;
    };
    reader.readAsDataURL(file);
  });

  removeImg?.addEventListener('click', () => {
    if (imageInput) imageInput.value = '';
    if (previewImg) previewImg.src = '';
    if (preview)   preview.hidden = true;
  });

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const submitBtn = document.getElementById('post-submit-btn');
    submitBtn?.classList.add('loading');

    try {
      const actionType = document.getElementById('post-action-type')?.value;
      const note       = document.getElementById('post-note')?.value.trim();
      const clubTag    = document.getElementById('post-club-tag')?.value.trim();
      const imageFile  = imageInput?.files?.[0];

      if (!actionType) { toast.error('Select an action type.'); return; }
      if (!note)       { toast.error('Describe what you did.'); return; }
      if (!currentUser.profile) { toast.warning('Complete the quiz first!'); return; }

      let imageObjectPath = '';
      if (imageFile) {
        // Get signed URL then upload directly to GCS
        const urlData = await api.get('/posts/upload-url', {
          user_id:      currentUser.id,
          filename:     imageFile.name,
          content_type: imageFile.type,
        });
        await fetch(urlData.upload_url, {
          method:  'PUT',
          headers: { 'Content-Type': imageFile.type },
          body:    imageFile,
        });
        imageObjectPath = urlData.object_path;
      }

      const p = currentUser.profile;
      await api.post('/posts', {
        user_id:           currentUser.id,
        display_name:      p.display_name || 'Anonymous',
        avatar_emoji:      p.avatar_emoji || '🌱',
        city:              p.city || 'India',
        action_type:       actionType,
        note,
        club_tag:          clubTag || null,
        image_object_path: imageObjectPath || null,
      });

      toast.success('Action shared! 🌿');
      closeModal();
      loadPosts(true);

    } catch (err) {
      toast.error('Failed to post: ' + err.message);
    } finally {
      submitBtn?.classList.remove('loading');
    }
  });
}

function _timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins  = Math.floor(diff / 60000);
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// Lazy triggers from page tab
function _ensureLeaderboard() {
  import('./leaderboard.js').then(m => m.initLeaderboard?.());
}
function _ensureClubs() {
  import('./clubs.js').then(m => m.initClubs?.());
}
