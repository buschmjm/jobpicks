# API — E2.9 scaffold

FastAPI application with stub service layer. Wire to Postgres (E2.2) by replacing in-memory stores.

## Run locally

```bash
# From repo root
pip install -e ".[dev]"
APP_ENV=development uvicorn api.main:app --reload --port 8000
```

Health: `GET http://127.0.0.1:8000/api/health`

## Auth (plan §12)

- `POST /api/auth/magic-link` — request sign-in link (rate-limit TODO in code comments)
- `GET /api/auth/verify?token=...` — single-use token, 15-min expiry; sets `session` cookie (HttpOnly, Secure in prod, SameSite=Lax)
- `GET /api/auth/me` — current user
- `POST /api/auth/logout`

In development, `magic-link` returns `dev_token` for click-through testing without SMTP.

Set `SECRET_KEY` in production.

## Onboarding

- `POST /api/onboarding/resume` — multipart upload, 5MB max, PDF/DOCX only
- `POST /api/onboarding/profile/confirm`
- `POST /api/onboarding/questionnaire`

## Deck

- `GET /api/deck/next`
- `POST /api/deck/swipe` — `{ queue_item_id, action, reason?, dwell_ms? }`
- `POST /api/deck/dwell`

## Todo

- `GET /api/todo?status=to_apply|applied|archived`
- `PATCH /api/todo/{id}` — update status
- `POST /api/todo/{id}/apply-click`
- `POST /api/todo/{id}/self-report`

## Frontend dev

See `web/README.md`. Vite proxies `/api` to port 8000.
