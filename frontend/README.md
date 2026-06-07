# EchoSQL Frontend

This is the Next.js TypeScript frontend for EchoSQL — a natural-language-to-SQL chatbot that proxies queries to a FastAPI backend.

Prerequisites

- Node.js 18+ or compatible
- npm or yarn

Installation

```bash
cd frontend
npm install
```

Environment

- Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_BASE` to your backend URL (default `http://localhost:8000`).

Development

```bash
npm run dev
# Open http://localhost:3000
```

Build & Production

```bash
npm run build
npm start
```

Project Layout

- `pages/` – Next.js pages: index, history, schema, admin
- `components/` – UI components: `QueryInput`, `ResultsTable`, `QueryHistory`
- `lib/api.ts` – API client used to call backend endpoints

API Contract (used by frontend)

- POST `/query` — body: { "nl": string } → response: { "sql": string, "rows": [...] }
- GET `/schema` — returns schema metadata (tables, columns) and embeddings summary
- GET `/history` — returns recent queries
- GET `/health` — service health

Example Query

Input: "Show top 10 products by revenue last month"

Expected backend response shape:

```json
{
  "sql": "SELECT p.name, SUM(oi.price * oi.quantity) AS revenue ...",
  "rows": [ { "name": "Widget", "revenue": 12345.67 }, ... ]
}
```

Troubleshooting

- Ensure `NEXT_PUBLIC_API_BASE` matches your FastAPI backend and CORS is enabled on the backend.
- If LLM backend is slow at first request, wait a minute for model to warm up.

Further work

- Add React Query or SWR hooks for caching (SWR is included in `package.json`).
- Add tests (Jest/RTL or Playwright) and Tailwind CSS for styling.
