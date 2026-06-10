# 🌍 EcoQuest — Carbon Footprint Awareness Platform

> A production-grade, AI-powered platform to help individuals understand, track, reduce, and sustain eco-friendly habits — deployed on Google Cloud Platform.

[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-deployed-brightgreen)](https://cloud.google.com/run)
[![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Gemini%202.5%20Flash-blue)](https://cloud.google.com/vertex-ai)
[![Firestore](https://img.shields.io/badge/Firestore-Native%20Mode-orange)](https://cloud.google.com/firestore)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com)

---

## 1. Problem Statement

India is home to 1.4 billion people, yet per-capita CO₂ awareness remains critically low. The average Indian emits **158 kg CO₂/month** — a number that is accelerating due to rising energy consumption, vehicle ownership, and fast-fashion adoption.

**The challenge:** Most carbon calculators are abstract, global, and generic. They don't account for India's specific grid intensity (0.708 kgCO₂/kWh), regional food culture, or income-aware sustainability options.

**EcoQuest solves this by:**
- Using **IPCC AR6 + MoEFCC India** emission factors calibrated for Indian context
- Providing **AI-coached, financially realistic** recommendations (students ≠ professionals)
- Gamifying reduction through **fair leaderboards** that reward improvement, not privilege
- Building **community accountability** through Eco Clubs and a social feed

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER BROWSER                               │
│   index.html · community.html · Vanilla JS Modules · Chart.js       │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ HTTPS
              ┌────────▼────────┐
              │   Cloud Run     │
              │  (Nginx Static) │  ← Frontend Service
              └────────┬────────┘
                       │ API calls / SSE
              ┌────────▼────────┐
              │   Cloud Run     │
              │  (FastAPI)      │  ← Backend Service
              └──┬──────┬───┬───┘
                 │      │   │
    ┌────────────▼─┐  ┌─▼───────────┐  ┌──────────────┐
    │  Firestore   │  │  Vertex AI  │  │ Cloud Storage│
    │ Native Mode  │  │  Gemini 2.5 │  │ (User Uploads│
    │              │  │  Flash      │  │  Signed URLs)│
    └──────────────┘  └─────────────┘  └──────────────┘
                 │
    ┌────────────▼─────────────────────────────────────┐
    │           Secret Manager                         │
    │  gemini-api-key · ecoquest-internal-token        │
    └──────────────────────────────────────────────────┘
                 │
    ┌────────────▼─────────────────────────────────────┐
    │     Cloud Scheduler (every Monday 00:00 IST)     │
    │     → POST /internal/challenges/rotate           │
    └──────────────────────────────────────────────────┘

    CI/CD: Cloud Build → Artifact Registry → Cloud Run
```

---

## 3. AI Design Decisions

### Why Gemini 2.5 Flash (not Pro)?
| Factor | Flash | Pro |
|---|---|---|
| Latency | ~500ms first token | ~2–4s first token |
| Cost | ~$0.075/1M tokens | ~$1.25/1M tokens |
| Streaming | ✅ Native SSE | ✅ |
| Context window | 1M tokens | 2M tokens |
| Suitability | Chat, coaching | Document analysis |

For a conversational sustainability coach with sub-second streaming responses, Flash is the optimal choice at 16× lower cost.

### Why streaming SSE for chat?
- Users perceive faster responses when tokens stream incrementally
- Sub-200ms time-to-first-token creates a sense of live interaction
- Avoids HTTP timeout on slow network connections (long-poll alternative)
- Allows mid-stream error recovery without full request failure

### Context injection strategy
Every chat request injects 7 profile fields into the system prompt:
```python
user_type, city, monthly_footprint_kg, biggest_emission_category,
completed_challenges[], current_streak, rank_tier
```
This transforms generic advice into hyper-personalized coaching without fine-tuning.

### Fallback when quota exceeded
1. Attempt Vertex AI streaming
2. On exception: fetch a pre-curated tip from `ai_fallback_tips` Firestore collection
3. Return the fallback with identical SSE format (transparent to frontend)
4. Log quota event to Cloud Logging for alerting

---

## 4. Leaderboard Fairness Rationale

### Why raw footprint ranking is inequitable
A car-dependent suburban family emits 300 kg/month structurally — they cannot compete with a city-dwelling student at 60 kg/month regardless of effort. Raw footprint ranking punishes geography, income, and life stage.

### Mathematical basis for improvement-percentage scoring

```
rank_score = (improvement_pct × 0.6) + (normalized_action_pts × 0.4)

improvement_pct = clamp(((baseline_kg − current_kg) / baseline_kg) × 100, 0, 100)

normalized_action_pts = (user_total_pts / max_pts_in_cohort) × 100
```

**Why 60/40 split?**
- Improvement (0.6) rewards actual behavioural change — the core mission
- Actions (0.4) rewards engagement and effort — prevents gaming via inactivity

**Why clamp at [0, 100]?**
- Negative improvement = 0 (no penalty for life events; encourage re-engagement)
- Over-100% is impossible (prevents div-by-zero and score inflation)

---

## 5. GCP Services Used

| Service | Purpose | Justification |
|---|---|---|
| Cloud Run (Backend) | FastAPI container | Serverless, scales to 0 in dev, cold start < 2s |
| Cloud Run (Frontend) | Nginx static server | Same deploy pipeline, no separate CDN needed |
| Firestore Native | Primary database | Document-native, real-time, India region support |
| Vertex AI Gemini 2.5 Flash | AI coaching | Streaming, 1M context, no API key management |
| Secret Manager | Credential storage | Zero hardcoded secrets, automatic rotation-ready |
| Cloud Storage | User image uploads | Signed URL pattern bypasses backend for uploads |
| Artifact Registry | Docker image registry | Immutable image tags, vulnerability scanning |
| Cloud Build | CI/CD pipeline | Native GCP integration, parallel steps, caching |
| Cloud Scheduler | Weekly challenge rotation | Managed cron, OIDC auth to Cloud Run |
| Cloud Logging | Observability | Structured logs, request ID correlation |

---

## 6. Emission Factor Sources

All factors are sourced from peer-reviewed government and IPCC publications:

| Category | Factor | Source |
|---|---|---|
| Petrol car | 0.192 kg CO₂/km | IPCC AR6 WG III, Table 10.SM.7 (2022) |
| Diesel car | 0.171 kg CO₂/km | IPCC AR6 WG III, Table 10.SM.7 (2022) |
| Electric vehicle | 0.053 kg CO₂/km | India grid intensity 0.708 kgCO₂/kWh × 0.075 kWh/km (MoEFCC NIR 2023) |
| Public transport | 0.041 kg CO₂/km | MoEFCC National Inventory Report 2020 (bus average) |
| Daily meat diet | 58 kg CO₂/month | IPCC AR6 Ch. 7 — Food Systems (2022) |
| Vegetarian diet | 5 kg CO₂/month | IPCC AR6 Ch. 7 — Food Systems (2022) |
| Energy (high bill) | 98 kg CO₂/month | India grid 0.708 kgCO₂/kWh × estimated kWh (MoEFCC 2023) |
| National average | 158 kg CO₂/month | MoEFCC National Inventory Report 2023 |

**Full references:**
- IPCC (2022). _Climate Change 2022: Mitigation of Climate Change._ Working Group III. Cambridge University Press.
- MoEFCC (2023). _India's Third National Communication to UNFCCC._ Ministry of Environment, Forest and Climate Change.

---

## 7. Local Development Guide

### Prerequisites
- Python 3.11+
- `gcloud` CLI authenticated (`gcloud auth application-default login`)
- GCP project with Firestore and Secret Manager enabled

### Setup

```bash
# Clone repo
git clone https://github.com/YOUR_REPO/ecoquest.git
cd ecoquest

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest pytest-asyncio  # dev deps

# Set environment variables
export GCP_PROJECT_ID=your-project-id
export GCS_BUCKET_NAME=your-bucket-name
export ENVIRONMENT=development

# Run backend (hot-reload)
uvicorn app.main:app --reload --port 8080
```

### Frontend
```bash
# Serve frontend locally (no build step needed)
cd frontend
python -m http.server 3000
# Open: http://localhost:3000
```

Configure the API URL in your browser console:
```js
window.__ECOQUEST_API__ = 'http://localhost:8080';
```

---

## 8. Deployment Guide

### Prerequisites
- `gcloud` CLI installed and authenticated
- GCP project created with billing enabled
- Project ID set: `gcloud config set project YOUR_PROJECT_ID`

### Deploy (single command)

```bash
bash deploy.sh
```

The script will:
1. Enable all required GCP APIs
2. Create Firestore database (native mode, nam5 region)
3. Create Artifact Registry repository
4. Create GCS bucket for uploads
5. Prompt for Gemini API key → store in Secret Manager
6. Build Docker images via Cloud Build
7. Deploy backend and frontend to Cloud Run
8. Create Cloud Scheduler job for weekly challenge rotation
9. Seed initial challenges into Firestore

**Expected output:**
```
🌍 EcoQuest deployed successfully!
  Frontend:  https://ecoquest-frontend-xxxx.a.run.app
  Backend:   https://ecoquest-backend-xxxx.a.run.app
  Health:    https://ecoquest-backend-xxxx.a.run.app/health
```

---

## 9. Testing Strategy

### Unit Tests

```bash
cd backend
pip install pytest pytest-asyncio
pytest tests/unit/ -v --tb=short
```

**Coverage targets:**
- `test_carbon_calc.py` — 100% function coverage, all transport/diet/energy combos
- `test_leaderboard.py` — Eligibility, scoring formula, tie-breaking, edge cases
- `test_challenges.py` — Streak logic, milestone detection, deduplication

### E2E Tests (Playwright)

```bash
pip install playwright pytest-playwright
playwright install chromium

# Start dev server first
uvicorn app.main:app --port 8080 &

pytest tests/e2e/ -v --headed   # --headed to see browser
```

### Coverage Report

```bash
pip install pytest-cov
pytest tests/unit/ --cov=app/services --cov-report=html
open htmlcov/index.html
```

---

## 10. Security Considerations

### Secrets
- All API keys loaded from **Secret Manager** at startup via `config.py`
- `settings.load_secrets()` runs in lifespan before the first request
- Zero hardcoded secrets anywhere in source code
- `.gitignore` explicitly excludes all `*.json` credential files

### IAM (Least Privilege)
- Cloud Run SA has only: `datastore.user`, `storage.objectCreator`, `secretmanager.secretAccessor`, `aiplatform.user`
- No `roles/owner` or `roles/editor` assigned
- Scheduler uses a dedicated SA with only `run.invoker` on the backend service

### Input Validation
- All request bodies validated with **Pydantic v2 strict mode**
- Max length enforced on every string field
- File uploads: MIME type validated server-side in `SignedUploadUrlRequest.validate_content_type`
- SQL injection: Not applicable (Firestore is NoSQL, all queries parameterised)
- Chat endpoint: 60 req/min sliding-window rate limit per IP

### HTTP Security Headers
Every response includes:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: [strict allowlist]
```

---

## 11. Future Improvements

| Priority | Feature | Effort |
|---|---|---|
| P0 | Firebase Auth integration (replace localStorage UUID) | 3 days |
| P0 | Redis-based rate limiting (multi-instance safe) | 1 day |
| P1 | Push notifications via Firebase Cloud Messaging | 2 days |
| P1 | Carbon offset marketplace integration | 1 week |
| P1 | Corporate/team dashboard for offices | 1 week |
| P2 | Mobile app (Flutter) using same backend API | 3 weeks |
| P2 | Regional emission factors (state-level India grid intensity) | 2 days |
| P2 | Pre-computed leaderboard via Cloud Tasks (10k+ users) | 3 days |
| P3 | Barcode scanner for product carbon footprint lookup | 1 week |
| P3 | Export personal carbon report as PDF | 2 days |
| P3 | Integration with Google Maps for route-based transport calc | 1 week |

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

*Built with ❤️ for the planet. Powered by Google Cloud Platform and Vertex AI Gemini 2.5 Flash.*
