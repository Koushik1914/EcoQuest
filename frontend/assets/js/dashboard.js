/**
 * EcoQuest — Dashboard Module
 * Stat cards, donut chart, trend chart, and personalised recommendations.
 */
import { currentUser, removeSkeleton } from './app.js';

let donutChart = null;
let trendChart  = null;

export function initDashboard() {
  window.addEventListener('routechange', ({ detail }) => {
    if (detail.hash === '#dashboard') renderDashboard();
  });
  window.addEventListener('quizCompleted', () => renderDashboard());

  // Initial render if on dashboard
  if (location.hash === '#dashboard' || !location.hash) renderDashboard();
}

async function renderDashboard() {
  const profile = currentUser.profile;

  // Show empty state if no profile
  const emptyEl   = document.getElementById('dashboard-empty');
  const statsGrid = document.querySelector('.stats-grid');
  const chartsRow = document.querySelector('.charts-row');
  const recsSection = document.querySelector('.recs-section');

  if (!profile) {
    if (emptyEl)    emptyEl.hidden = false;
    if (statsGrid)  statsGrid.style.display = 'none';
    if (chartsRow)  chartsRow.style.display = 'none';
    if (recsSection) recsSection.style.display = 'none';
    return;
  }

  if (emptyEl)    emptyEl.hidden = true;
  if (statsGrid)  statsGrid.style.display = '';
  if (chartsRow)  chartsRow.style.display = '';
  if (recsSection) recsSection.style.display = '';

  _renderStatCards(profile);
  _renderDonutChart(profile);
  await _renderTrendChart();
  _renderRecommendations(profile);

  // Greeting
  const greet = document.getElementById('dashboard-greeting');
  const hour = new Date().getHours();
  const tod = hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening';
  if (greet) greet.textContent = `Good ${tod}, ${profile.display_name || 'friend'}! Here's your impact today.`;
}

function _renderStatCards(profile) {
  const kg     = profile.total_monthly_kg?.toFixed(1) ?? '--';
  const base   = profile.baseline_kg || 0;
  const curr   = profile.total_monthly_kg || 0;
  const redPct = base > 0 ? (((base - curr) / base) * 100).toFixed(1) : null;
  const saved  = (profile.total_co2_saved_kg || 0).toFixed(1);
  const streak = profile.current_streak || 0;

  _setEl('stat-footprint', kg);
  _setEl('stat-reduction', redPct !== null ? `${redPct >= 0 ? '-' : '+'}${Math.abs(redPct)}%` : '--%');
  _setEl('stat-streak', streak);
  _setEl('stat-co2-saved', `${saved} kg`);
  _setEl('stat-rank-tier', _rankLabel(profile.rank_tier || 'seedling'));

  const badge = document.getElementById('stat-rating-badge');
  if (badge && profile.rating) {
    badge.className = `stat-card__badge badge--${profile.rating}`;
    badge.textContent = _ratingLabel(profile.rating);
  }

  // Challenges this week — read from localStorage cache
  const weekChallenges = parseInt(localStorage.getItem('ecoquest_week_challenges') || '0');
  _setEl('stat-challenges-week', weekChallenges);
}

function _renderDonutChart(profile) {
  const canvas = document.getElementById('donut-chart');
  if (!canvas || !window.Chart) return;

  const bd = profile.breakdown || {};
  const labels  = ['Transport', 'Food', 'Energy', 'Shopping'];
  const data    = [bd.transport_pct || 0, bd.food_pct || 0, bd.energy_pct || 0, bd.shopping_pct || 0];
  const colors  = ['#16a34a', '#84cc16', '#065f46', '#a3e635'];
  const bgColors = ['rgba(22,163,74,.15)','rgba(132,204,22,.15)','rgba(6,95,70,.15)','rgba(163,230,53,.15)'];

  if (donutChart) donutChart.destroy();
  donutChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors,
        borderColor:     colors.map(() => '#fff'),
        borderWidth:     3,
        hoverOffset:     8,
      }],
    },
    options: {
      responsive:       true,
      maintainAspectRatio: true,
      cutout:           '68%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed.toFixed(1)}%`,
          },
        },
      },
    },
  });

  // Custom legend
  const legendEl = document.getElementById('donut-legend');
  if (legendEl) {
    legendEl.innerHTML = labels.map((lbl, i) => `
      <div class="legend-item">
        <span class="legend-dot" style="background:${colors[i]}"></span>
        <span>${lbl}: ${data[i].toFixed(1)}%</span>
      </div>
    `).join('');
  }
}

async function _renderTrendChart() {
  const canvas = document.getElementById('trend-chart');
  if (!canvas || !window.Chart) return;

  // Build trend from localStorage snapshots (backend would provide 6-month history)
  const snapshots = JSON.parse(localStorage.getItem('ecoquest_snapshots') || '[]');

  // Always add current month if profile exists
  if (currentUser.profile?.total_monthly_kg) {
    const now = new Date();
    const label = now.toLocaleString('en-IN', { month: 'short', year: '2-digit' });
    const existing = snapshots.find(s => s.label === label);
    if (!existing) {
      snapshots.push({ label, value: currentUser.profile.total_monthly_kg });
      // Keep last 6
      while (snapshots.length > 6) snapshots.shift();
      localStorage.setItem('ecoquest_snapshots', JSON.stringify(snapshots));
    }
  }

  const labels = snapshots.length
    ? snapshots.map(s => s.label)
    : ['6mo ago','5mo ago','4mo ago','3mo ago','2mo ago','This month'];
  const values = snapshots.length
    ? snapshots.map(s => s.value)
    : [null,null,null,null,null,null];

  const indiaAvg = Array(labels.length).fill(158);

  if (trendChart) trendChart.destroy();
  trendChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Your footprint',
          data: values,
          borderColor:     '#16a34a',
          backgroundColor: 'rgba(22,163,74,.1)',
          tension:         0.4,
          fill:            true,
          pointBackgroundColor: '#16a34a',
          pointRadius:     5,
          pointHoverRadius:7,
          spanGaps:        true,
        },
        {
          label: 'India average (158 kg)',
          data: indiaAvg,
          borderColor: '#d97706',
          borderDash:  [6, 4],
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
          tension: 0,
        },
      ],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: { font: { size: 11 }, color: '#6b7280' },
        },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1) ?? '?'} kg`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(0,0,0,.05)' },
          ticks: { callback: v => `${v} kg`, color: '#6b7280', font: { size: 11 } },
        },
        x: {
          grid: { display: false },
          ticks: { color: '#6b7280', font: { size: 11 } },
        },
      },
    },
  });
}

function _renderRecommendations(profile) {
  const grid = document.getElementById('recs-grid');
  if (!grid) return;
  removeSkeleton(grid);

  // Derive top recommendations from profile
  const bd  = profile.breakdown || {};
  const topCat = Object.entries(bd).reduce((a,b) => (b[1] > a[1] ? b : a), ['none', 0])[0];
  const catLabel = { transport_pct:'transport', food_pct:'food', energy_pct:'energy', shopping_pct:'shopping' }[topCat] || 'general';
  const kg = profile.total_monthly_kg || 0;

  const recs = _getRecommendations(catLabel, kg);
  grid.innerHTML = recs.map(rec => `<div class="rec-card">${rec}</div>`).join('');
}

function _getRecommendations(topCat, kg) {
  const maps = {
    transport: [
      `🚌 <strong>Take public transit twice a week</strong> — saves ~${(kg * 0.13).toFixed(1)} kg CO₂/month.`,
      `🚲 <strong>Cycle for trips under 5 km</strong> — cuts your transport emissions to near zero.`,
      `🚗 <strong>Carpool on your busiest commute day</strong> — halves per-km emissions instantly.`,
    ],
    food: [
      `🥗 <strong>One plant-based day per week</strong> — saves ~${(kg * 0.07).toFixed(1)} kg CO₂/month.`,
      `🌾 <strong>Replace red meat with pulses twice weekly</strong> — cuts food emissions by ~17%.`,
      `🛒 <strong>Buy local seasonal produce</strong> — reduces food-mile emissions by up to 10%.`,
    ],
    energy: [
      `🔌 <strong>Unplug standby devices nightly</strong> — saves ~${(kg * 0.08).toFixed(1)} kg CO₂/month.`,
      `🌡️ <strong>Set AC to 24°C</strong> instead of 18°C — saves ~${(kg * 0.09).toFixed(1)} kg CO₂/month.`,
      `💡 <strong>Switch to LED bulbs</strong> — 75% less electricity per fitting, lasting 10× longer.`,
    ],
    shopping: [
      `🛍️ <strong>Consolidate to monthly bulk shopping</strong> — saves ~${(kg * 0.12).toFixed(1)} kg CO₂/month.`,
      `♻️ <strong>Buy one second-hand item this month</strong> — 80% lower carbon vs new.`,
      `🌿 <strong>Choose products with eco-certifications</strong> for your most frequent purchases.`,
    ],
    general: [
      `🌱 <strong>Complete the Carbon Quiz</strong> to get personalised tips based on your data.`,
      `⚡ <strong>Start a 7-day challenge streak</strong> — earn 25 bonus points and build lasting habits.`,
      `👥 <strong>Join an Eco Club</strong> to multiply your individual impact through collective action.`,
    ],
  };
  return maps[topCat] || maps.general;
}

function _setEl(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function _rankLabel(tier) {
  const labels = {
    seedling:          '🌱 Seedling',
    eco_explorer:      '🍃 Eco Explorer',
    climate_champion:  '🌍 Climate Champion',
    planet_protector:  '🏆 Planet Protector',
  };
  return labels[tier] || '🌱 Seedling';
}

function _ratingLabel(rating) {
  return { green: '🟢 Green', yellow: '🟡 Yellow', red: '🔴 Red' }[rating] || '';
}
