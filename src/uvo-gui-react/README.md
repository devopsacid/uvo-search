# uvo-gui-react

React SPA replacing the NiceGUI public frontend for UVO procurement search. Serves Slovak-language procurement data from the `uvo_api` backend (port 8001).

## Dev

```bash
npm install
npm run dev    # Vite dev server on http://localhost:5174, /api proxied to :8001
npm run build  # Production build to dist/
npm run test   # Vitest unit tests
npm run lint   # ESLint
```

## Docker

Built as part of the repo stack:

```bash
docker compose up gui-react   # serves on http://localhost:8090
```
