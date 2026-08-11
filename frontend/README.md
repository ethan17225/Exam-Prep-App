# Exam Prep — frontend

Angular 21 (standalone, zoneless, signals) single-page app. All API calls go through the
relative `/api` prefix — proxied to the backend by `proxy.conf.json` in development and by
nginx (`nginx.conf`) in the Docker image. There are no environment files and no absolute
API URLs; keep it that way.

## Development

```bash
npm ci
npm start          # dev server on http://localhost:4200, proxies /api to localhost:8000
```

The backend must be running on port 8000 (see `../backend`).

## Checks

```bash
npm run build          # production build (budgets enforced)
npm test               # vitest unit tests (pure logic: grading parity, helpers)
npm run lint           # angular-eslint
npm run format:check   # prettier (100 cols, single quotes)
```

All four run in CI on every push/PR that touches `frontend/` (`.github/workflows/frontend.yml`).

## Conventions

Frontend conventions live in `../.claude/skills/exam-ui-practices/SKILL.md` — read it before
adding pages or changing state/HTTP/error patterns. Highlights: signals only (no store, no
`BehaviorSubject`), constructor DI, `@if`/`@for` control flow, shared helpers and domain types
in `services/exam.service.ts`, one 640px mobile breakpoint.

Client-side grading (`isAnswerCorrect` in `exam.service.ts`) is a port of
`../backend/src/grading/service.py` — change them together, and keep the parity tests in
`exam.service.spec.ts` green.

## Docker

`Dockerfile` builds the app and serves it via nginx with security headers
(`security-headers.conf`) and the `/api` reverse proxy. Note: `inlineCritical` is disabled in
`angular.json` because the CSP (`script-src 'self'`) blocks the inline `onload` handler the
critical-CSS inliner emits.
