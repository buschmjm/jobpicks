# Web — E2.10 swipe deck UI

React + Vite + TypeScript + Tailwind v4.

## Run dev server

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173 — API calls proxy to `http://127.0.0.1:8000` (start API separately).

## Build for production

```bash
npm run build
```

Output in `web/dist/` — served by FastAPI when present (`api/main.py`).
