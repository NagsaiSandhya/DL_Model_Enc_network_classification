# A Novel Multimodel Deep Learning Framework for Encrypted Traffic Classification

Web application: upload a PCAP/PCAPNG capture, classify it with the existing trained model (**VPN vs non-VPN**),
view plain-language results with charts, and download a report.

## Architecture

```text
Frontend (React + Vite, :5173)
   │  POST /api/analyze (multipart), GET /api/*
   ▼
backend (Express, :5000) ──Mongoose──▶ MongoDB (optional history)
   │  forwards capture via HTTP FormData (no shell)
   ▼
ml_service (FastAPI, :8000) ──imports──▶ src/predict.py::predict_capture
                                     ▶ models/vpn_classifier.pkl (RF v1.0.0, test acc 0.963)
```

- Feature extraction is **never reimplemented**: the ML service calls the existing `src/` pipeline (same 24
  features, same schema check, same label mapping `nonvpn→0, vpn→1`).
- No mock predictions: every result comes from the saved scikit-learn Pipeline.
- History works without MongoDB (in-memory, clearly labeled temporary).

## Prerequisites

- Windows, VS Code, CMD
- Python `.venv` in `demo1/` (has scikit-learn, scapy, pandas, torch; FastAPI/uvicorn/httpx were added)
- Node.js 24+ and npm
- Optional: MongoDB for persistent history

## Run (3 terminals, CMD)

Terminal 1 — Python ML service:

```cmd
cd C:\MAJOR-PROJECT\demo1
.venv\Scripts\activate
python -m uvicorn ml_service.app:app --port 8000
```

Terminal 2 — Express backend:

```cmd
cd C:\MAJOR-PROJECT\demo1\backend
copy .env.example .env
npm install
npm start
```

Terminal 3 — React frontend:

```cmd
cd C:\MAJOR-PROJECT\demo1\Frontend
copy .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`. All three services must be running.

| Service | URL | Health |
|---|---|---|
| Frontend | http://localhost:5173 | page loads |
| Backend | http://localhost:5000 | `GET /api/health` |
| ML service | http://127.0.0.1:8000 | `GET /health` (docs at `/docs`) |

Port conflicts: change `PORT` (backend `.env`), `--port` (uvicorn), or `server.port` (`Frontend/vite.config.js`;
keep `VITE_API_BASE_URL` / `FRONTEND_ORIGIN` / `ML_SERVICE_URL` consistent).

## API endpoints (backend)

- `GET /api/health` — `{ status, mlServiceReachable, historyPersistent }`
- `GET /api/model-info` — tasks, model version, 24-feature schema, verified metrics
- `POST /api/analyze` — multipart field `file` (.pcap/.pcapng, ≤200 MB default) → real analysis JSON
- `GET /api/analysis` — history (`{ items, persistent }`)
- `GET /api/analysis/:id` — single result
- `GET /api/analysis/:id/report?format=json|csv` — download (attachment)

ML service: `GET /health`, `GET /model-info`, `POST /predict` (multipart `file`).

## Tests (all executed, all passing)

- ML service (FastAPI TestClient, real captures): health, model-info, non-VPN→`nonvpn` (0.98),
  VPN→`vpn` (0.94), bad extension→400, empty→400.
- Backend (`cd backend && npm test`, 10/10): health, model-info, valid `.pcapng` + `.pcap` uploads with
  correct class→probability mapping, temp-file cleanup, unsupported extension, empty file, malformed capture
  (no traceback leak), 413 size limit, history + JSON/CSV reports, ML-down→friendly 503.
- Frontend: `npm run build` passes (43 modules); pages wired only to real backend endpoints.
- Full E2E (`node e2e_check.js` from `demo1/`): frontend shell + backend + ML service with real VPN and
  non-VPN captures — **E2E ALL PASSED** (both predicted correctly, report matches).
- Existing ML tests preserved: `python src/acceptance_tests.py` (13/13).

## Known limitations

- VPN vs non-VPN only; no validated application-level (chat/email/video/…) classification.
- First 20,000 packets per capture analyzed (same rule as training); uploads capped at 200 MB.
- Class scores are raw RandomForest vote fractions, not calibrated probabilities.
- Val accuracy (0.815) trails test (0.963): performance varies by traffic type; see `results/metrics/`.
- History is in-memory unless `MONGODB_URI` is set; never stores PCAP bytes or payloads.
