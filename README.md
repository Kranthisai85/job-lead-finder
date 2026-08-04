# lead-finder

Production-ready monorepo scaffold for a startup lead discovery platform.

## Stack

- Backend: FastAPI, Python 3.12, Beanie, Motor, MongoDB, APScheduler, Playwright
- Frontend: React, Vite, Tailwind CSS, React Router, TanStack Query, Axios
- Infra: Docker, Docker Compose, Nginx-ready setup

## Structure

- `backend/`
- `frontend/`
- `docker/`
- `docs/`
- `scripts/`

## Start

1. Optionally adjust `backend/.env`.
2. Optionally adjust `VITE_API_URL` in root-level `.env` (defaults to `http://localhost:8001`).
3. Run:

```bash
docker compose up -d
```
