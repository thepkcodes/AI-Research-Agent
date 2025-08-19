# AI Research Agent

A full‑stack research assistant that searches the web, extracts content, and generates concise summaries using Google Gemini models.

- Backend: FastAPI (Python) — search, scrape, summarize, and store history in SQLite
- Frontend: Next.js (React) — UI to submit queries and view results/history

## Project Structure

```
ai-research-agent/
├─ backend/
│  ├─ main.py                 # FastAPI app (search/scrape/summarize + SQLite history)
│  ├─ requirements.txt        # Python dependencies
│  ├─ .env                    # Environment variables (local, not committed normally)
│  └─ research_history.db     # SQLite DB file (created at runtime)
└─ frontend/
   └─ my-app/                 # Next.js app
      ├─ package.json
      ├─ src/ | pages/ | public/
      └─ next.config.mjs
```

## Prerequisites

- Python 3.11+ (project uses venv; path shows Python 3.13 in .venv)
- Node.js 18+ (for Next.js 15)
- A Google AI Studio API key (Gemini): set as GEMINI_API_KEY

## Backend (FastAPI)

### Setup

```
# from repo root
cd backend
python -m venv .venv
# PowerShell
. .venv/Scripts/Activate.ps1
# or cmd
# .venv\Scripts\activate.bat

pip install -r requirements.txt
```

Create a .env file in backend/:

```
# backend/.env
GEMINI_API_KEY=your_google_ai_studio_key_here
# Optional, defaults to gemini-2.0-flash-001
GEMINI_MODEL=gemini-2.0-flash-001
```

### Run

```
# from backend/
python main.py
# or explicitly
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will start on http://localhost:8000. CORS is configured to allow http://localhost:3000 (frontend).

### API Endpoints

- GET `/` — health check: { "message": "API is live" }
- POST `/research` — perform a web search + extract + summarize
  - Request body:
    ```json
    {
      "text": "your query",
      "num_results": 5
    }
    ```
  - Response:
    ```json
    {
      "query": "...",
      "results": [ { "title": "...", "url": "...", "snippet": "..." } ],
      "summary": "..."
    }
    ```
- GET `/history` — list saved research runs (latest first)
- GET `/history/{id}` — get a single saved run by ID

### Data Storage

- SQLite DB file at `backend/research_history.db`
- Each `/research` call is saved with query, raw results, and generated summary.

## Frontend (Next.js)

```
cd frontend/my-app
npm install
npm run dev
```

- Dev server: http://localhost:3000
- Ensure the backend is running on http://localhost:8000.

If your frontend fetches the backend, keep the default CORS origin (http://localhost:3000) or update it in `backend/main.py` if you change ports/origins.

## How It Works

1. Search: Scrapes DuckDuckGo HTML results (no API key required) to get top links/snippets.
2. Extract: Fetches each page and extracts readable text (filters scripts/styles/nav/ads; falls back to snippet).
3. Summarize: Sends a compact prompt to Google Gemini via `google.genai` to produce concise bullet points.
4. Persist: Saves each run to SQLite with timestamp; history endpoints expose recent runs.

## Environment & Secrets

- Configure secrets via backend/.env. Never commit real keys.
- Required: `GEMINI_API_KEY`
- Optional: `GEMINI_MODEL` (defaults to `gemini-2.0-flash-001`)

## Development Tips

- Python dependencies are pinned in `backend/requirements.txt`.
- When adjusting CORS or ports, update `allow_origins` in `backend/main.py`.
- If requests to certain sites are blocked or non‑HTML, extractor returns empty and falls back to the search snippet.
- You can switch summarization providers by replacing the Gemini client usage in `summarize_content`.

## Running Both Services Concurrently

Open two terminals:

- Terminal 1 (backend):
  ```
  cd backend
  . .venv/Scripts/Activate.ps1
  uvicorn main:app --reload
  ```
- Terminal 2 (frontend):
  ```
  cd frontend/my-app
  npm run dev
  ```

## Troubleshooting

- 401/permission errors on summarize: verify `GEMINI_API_KEY` and model access in Google AI Studio.
- CORS errors in browser: ensure frontend uses http://localhost:3000 and backend allows that origin.
- Empty or short summaries: some pages block scraping or have little text; try increasing `num_results`.
- DB locked on Windows: stop the app before manually editing/deleting `research_history.db`.

## License

See LICENSE.
