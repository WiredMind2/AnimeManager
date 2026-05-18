## AnimeManager Next Web

This directory hosts the new Next.js App Router frontend for AnimeManager.
It replaces the legacy Jinja + HTMX `/ui/*` pages while keeping Python as
the backend source of truth.

### Backend expectations

- Python API server running (default `http://127.0.0.1:8081`)
- Next.js dev server running in this directory
- `/ui/*` SSE/WS endpoints available from Python

### Environment

Copy `.env.example` to `.env.local` and adjust values if needed.

```bash
cp .env.example .env.local
```

### Development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Build

```bash
npm run build
npm run start
```

### Route coverage

Implemented App Router pages:

- `/library`
- `/anime/[id]`
- `/anime/[id]/watch`
- `/anime/[id]/characters`
- `/downloads`
- `/torrents`
- `/logs`
- `/settings`
- `/offline`

Key backend contract endpoint:

- `GET /ui/api/meta`

This advertises stream paths and UI API versioning for the frontend.

### Notes

- Next server actions for core anime mutations live in `src/app/actions/anime.ts`.
- Client stream components use EventSource/WebSocket and are kept isolated in `src/components`.
