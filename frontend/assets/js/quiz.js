/**
 * EcoQuest — Quiz Module
 * 5-step multi-form quiz with per-step validation and API submission.
 */
import { api, currentUser, saveProfile, toast } from './app.js';

const TOTAL_STEPS = 5;
let currentStep = 1;

export function initQuiz() {
  const form    = document.getElementById('quiz-form');
  const prevBtn = document.getElementById('quiz-prev-btn');
  const nextBtn = document.getElementById('quiz-next-btn');
  const submitBtn = document.getElementById('quiz-submit-btn');

  if (!form) return;

  // Show/hide km field based on transport mode
  const modeSelect = document.getElementById('transport-mode');
  const kmGroup    = document.getElementById('km-group');
  modeSelect?.addEventListener('change', () => {
    const zeroEmission = ['bike','walk','wfh'].includes(modeSelect.value);
    if (kmGroup) kmGroup.style.display = zeroEmission ? 'none' : 'block';
    if (zeroEmission) {
      const kmInput = document.getElementById('weekly-km');
      if (kmInput) kmInput.value = '0';
    }
  });

  prevBtn?.addEventListener('click', () => goToStep(currentStep - 1));
  nextBtn?.addEventListener('click', () => {
    if (validateStep(currentStep)) goToStep(currentStep + 1);
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!validateStep(currentStep)) return;
    await submitQuiz(form, submitBtn);
  });

  // Keyboard navigation within radio cards
  form.querySelectorAll('.radio-group').forEach(group => {
    group.addEventListener('keydown', e => {
      const radios = [...group.querySelectorAll('input[type="radio"]')];
      const idx = radios.findIndex(r => r === document.activeElement);
      if (idx === -1) return;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        radios[(idx + 1) % radios.length].focus();
        radios[(idx + 1) % radios.length].checked = true;
      }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        radios[(idx - 1 + radios.length) % radios.length].focus();
        radios[(idx - 1 + radios.length) % radios.length].checked = true;
      }
    });
  });
}

function goToStep(step) {
  if (step < 1 || step > TOTAL_STEPS) return;

  // Hide current, show next
  document.getElementById(`quiz-step-${currentStep}`)?.setAttribute('hidden', '');
  const nextEl = document.getElementById(`quiz-step-${step}`);
  nextEl?.removeAttribute('hidden');

  currentStep = step;
  _updateProgress();

  // Button visibility
  const prevBtn   = document.getElementById('quiz-prev-btn');
  const nextBtn   = document.getElementById('quiz-next-btn');
  const submitBtn = document.getElementById('quiz-submit-btn');
  if (prevBtn)   prevBtn.disabled = step === 1;
  if (nextBtn)   nextBtn.hidden   = step === TOTAL_STEPS;
  if (submitBtn) submitBtn.hidden = step !== TOTAL_STEPS;

  // Focus first input in new step
  nextEl?.querySelector('input,select,textarea')?.focus();
}

function _updateProgress() {
  const bar = document.getElementById('quiz-progress-bar');
  const pct = (currentStep / TOTAL_STEPS) * 100;
  if (bar) {
    bar.style.width = `${pct}%`;
    bar.setAttribute('aria-valuenow', currentStep);
    bar.setAttribute('aria-label', `Step ${currentStep} of ${TOTAL_STEPS}`);
  }
  document.querySelectorAll('.step-dot').forEach(dot => {
    const s = parseInt(dot.dataset.step);
    dot.classList.toggle('active', s === currentStep);
    dot.classList.toggle('done',   s < currentStep);
  });
}

function validateStep(step) {
  let valid = true;

  const clearError = id => {
    const el = document.getElementById(id);
    if (el) el.hidden = true;
  };
  const showError = (fieldId, errorId, msg) => {
    const el = document.getElementById(errorId);
    if (el) { el.textContent = msg; el.hidden = false; }
    const field = document.getElementById(fieldId);
    field?.classList.add('error');
    field?.focus();
    valid = false;
  };

  if (step === 1) {
    clearError('transport-mode-error');
    clearError('weekly-km-error');
    const mode = document.getElementById('transport-mode')?.value;
    const km   = parseFloat(document.getElementById('weekly-km')?.value || '0');
    if (!mode) { showError('transport-mode', 'transport-mode-error', 'Please select a transport mode.'); }
    else if (!['bike','walk','wfh'].includes(mode) && (isNaN(km) || km < 0 || km > 2000)) {
      showError('weekly-km', 'weekly-km-error', 'Enter km between 0 and 2000.');
    }
  }
  if (step === 2) {
    clearError('diet-error');
    const checked = document.querySelector('input[name="meat_frequency"]:checked');
    if (!checked) { showError(null, 'diet-error', 'Please select your meat frequency.'); valid = false; }
  }
  if (step === 3) {
    clearError('energy-error');
    const checked = document.querySelector('input[name="energy_bill"]:checked');
    if (!checked) { showError(null, 'energy-error', 'Please select your energy bill range.'); valid = false; }
  }
  if (step === 4) {
    clearError('recycling-error');
    clearError('shopping-error');
    if (!document.getElementById('recycling')?.value) {
      showError('recycling', 'recycling-error', 'Please select your recycling habit.'); }
    if (!document.querySelector('input[name="shopping_frequency"]:checked')) {
      showError(null, 'shopping-error', 'Please select your shopping frequency.'); valid = false; }
  }
  if (step === 5) {
    clearError('name-error'); clearError('user-type-error'); clearError('city-error');
    const name = document.getElementById('display-name')?.value.trim();
    const type = document.getElementById('user-type')?.value;
    const city = document.getElementById('city')?.value.trim();
    if (!name || name.length < 1) showError('display-name','name-error','Please enter your name.');
    if (!type) showError('user-type','user-type-error','Please select your user type.');
    if (!city || city.length < 2) showError('city','city-error','Please enter your city.');
  }
  return valid;
}

async function submitQuiz(form, submitBtn) {
  submitBtn?.classList.add('loading');
  submitBtn && (submitBtn.disabled = true);

  try {
    const data = new FormData(form);
    const mode = data.get('transport_mode') || '';
    const km   = parseFloat(data.get('weekly_km') || '0');

    const payload = {
      user_id:      currentUser.id,
      display_name: data.get('display_name').trim(),
      transport: {
        mode:      mode,
        weekly_km: isNaN(km) ? 0 : km,
      },
      diet:      { meat_frequency: data.get('meat_frequency') },
      energy:    { monthly_bill_inr: data.get('energy_bill') },
      lifestyle: {
        recycling:          data.get('recycling'),
        shopping_frequency: data.get('shopping_frequency'),
      },
      profile: {
        user_type: data.get('user_type'),
        city:      data.get('city').trim(),
      },
    };

    const result = await api.post('/quiz/submit', payload);

    // Persist profile locally
    saveProfile({
      user_id:          currentUser.id,
      display_name:     payload.display_name,
      total_monthly_kg: result.total_monthly_kg,
      baseline_kg:      result.is_baseline ? result.total_monthly_kg : (currentUser.profile?.baseline_kg || result.total_monthly_kg),
      breakdown:        result.breakdown,
      rating:           result.rating,
      vs_national_avg:  result.vs_national_avg_pct,
      user_type:        payload.profile.user_type,
      city:             payload.profile.city,
      avatar_emoji:     '🌱',
      total_points:     currentUser.profile?.total_points || 0,
      current_streak:   currentUser.profile?.current_streak || 0,
    });

    toast.success(`Your footprint: ${result.total_monthly_kg.toFixed(1)} kg CO₂/month!`);

    // Navigate to dashboard
    window.location.hash = '#dashboard';
    window.dispatchEvent(new CustomEvent('quizCompleted', { detail: result }));

  } catch (err) {
    toast.error('Failed to submit quiz: ' + err.message);
  } finally {
    submitBtn?.classList.remove('loading');
    if (submitBtn) submitBtn.disabled = false;
  }
}
