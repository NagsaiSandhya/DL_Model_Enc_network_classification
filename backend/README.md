# Encrypted Traffic Backend

Express API that validates PCAP uploads and proxies them to the Python ML service (`ml_service`).

## Run (Windows CMD)

```cmd
cd path\to\demo1\backend
copy .env.example .env
npm install
npm start
```

Backend: `http://localhost:5000`. Requires the ML service on `http://127.0.0.1:8000`:

```cmd
cd path\to\demo1
.venv\Scripts\activate
python -m uvicorn ml_service.app:app --port 8000
```

## Endpoints

- `GET /api/health` — backend + ML reachability
- `GET /api/model-info` — tasks, version, verified metrics (from ML service)
- `POST /api/analyze` — multipart `file` (.pcap/.pcapng)
- `GET /api/analysis` — history (in-memory unless `MONGODB_URI` set)
- `GET /api/analysis/:id` — single result
- `GET /api/analysis/:id/report?format=json|csv` — download report

History persists to MongoDB only when `MONGODB_URI` is configured; otherwise the core classify workflow still works and responses say so.
