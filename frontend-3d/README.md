# JOBFinder 3D Frontend

Cinematic React frontend (Vite + React Three Fiber + Tailwind + Framer Motion).
This is a **separate, self-contained app**. It does not replace or modify the
existing `frontend/public/chat.html` or `dashboard.html`.

## Run

```bash
cd frontend-3d
npm install
npm run dev   # http://localhost:3000
```

The backend FastAPI app should be running on `http://localhost:8000`. The Vite
dev server proxies `/ingestion`, `/auth`, and `/health` to it (see
`vite.config.js`).

## Pages
- `/`      Cinematic 3D landing (animated starfield hero)
- `/jobs`  Live job feed from `GET /ingestion/jobs` (the shared pool)
- `/login` Sign in / sign up against `/auth/login` and `/auth/register`

## Notes
- Wired to Phase 1 ingestion so the feed shows real pool jobs.
- Token stored in localStorage and sent as `Authorization: Bearer`.
- Build for production with `npm run build` (outputs to `dist/`).
