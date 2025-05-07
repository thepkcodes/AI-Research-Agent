from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import requests
from bs4 import BeautifulSoup
import urllib.parse
from google import genai
import os
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv

# Load env
load_dotenv()

# Configure your API key
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-001")

app = FastAPI(title="Research Agent API")

# Allow Next.js on localhost:3000 to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# — Pydantic models —
class Query(BaseModel):
    text: str
    num_results: Optional[int] = 5

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str

class ResearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    summary: str

# — SQLite setup —
DB = "research_history.db"

def init_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_history (
          id        INTEGER PRIMARY KEY AUTOINCREMENT,
          query     TEXT NOT NULL,
          results   TEXT NOT NULL,
          timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_research(query: str, payload: dict):
    conn = sqlite3.connect(DB, check_same_thread=False)
    cur = conn.cursor()
    ts = datetime.now().isoformat()
    cur.execute(
        "INSERT INTO research_history (query, results, timestamp) VALUES (?, ?, ?)",
        (query, json.dumps(payload), ts)
    )
    conn.commit()
    conn.close()

def get_research_history():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM research_history ORDER BY timestamp DESC")
    rows = cur.fetchall()
    conn.close()
    out = []
    for r in rows:
        rec = dict(r)
        rec["results"] = json.loads(rec["results"])
        out.append(rec)
    return out

def get_research_by_id(rid: int):
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM research_history WHERE id = ?", (rid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    rec = dict(row)
    rec["results"] = json.loads(rec["results"])
    return rec

@app.on_event("startup")
def on_startup():
    init_db()

# — DuckDuckGo scraping —
def search_duckduckgo(query: str, num_results: int = 5):
    q = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={q}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print("DuckDuckGo error:", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    hits = []
    for block in soup.select(".result"):
        link = block.select_one(".result__title a")
        if not link:
            continue
        title = link.get_text(strip=True)
        raw = link.get("href", "")
        if raw.startswith("/l/"):
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            href = qs.get("uddg", [raw])[0]
        else:
            href = raw
        snippet_el = block.select_one(".result__snippet")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        hits.append({"title": title, "url": href, "snippet": snippet})
        if len(hits) >= num_results:
            break

    return hits

# — Content extraction (with snippet fallback) —
def extract_content(url: str, max_length: int = 8000):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        if "text/html" not in r.headers.get("Content-Type", ""):
            return ""
    except Exception:
        return ""

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script","style","nav","footer","header","aside","iframe","noscript","advertisement"]):
        tag.extract()

    main = None
    for sel in ["main","article",".content",".post",".article",".main-content"]:
        found = soup.select(sel)
        if found:
            main = found
            break

    if main:
        text = " ".join(sec.get_text(separator=" ", strip=True) for sec in main)
    else:
        paras = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paras) if paras else soup.get_text(separator=" ", strip=True)

    text = " ".join(text.split())
    return text[:max_length] + "..." if len(text) > max_length else text

# — Summarization (new v1.0.0 interface) —
def summarize_content(query: str, items: List[dict]):
    system = "You are a research assistant that creates concise, accurate summaries."
    user = f'Query: "{query}"\n\n'
    for i, it in enumerate(items[:5], 1):
        excerpt = it["content"][:800]
        user += (
            f"Article {i}:\n"
            f"Title: {it['title']}\n"
            f"URL: {it['url']}\n\n"
            f"Excerpt: {excerpt}\n\n---\n\n"
        )
    user += "Please provide a concise summary in 5–10 bullet points."

    try:
        client = genai.Client(api_key=API_KEY)
        response = client.models.generate_content(
            model = MODEL,
            contents = user,
        )
        return response.text.strip()
    except Exception as e:
        # return the real error so you can debug
        return f"Failed to generate summary: {e}"

# — Endpoints —
@app.post("/research", response_model=ResearchResponse)
async def perform_research(q: Query):
    raw = search_duckduckgo(q.text, q.num_results)
    if not raw:
        raise HTTPException(404, detail="No search results found")

    enriched = []
    for hit in raw:
        content = extract_content(hit["url"]) or hit["snippet"]
        enriched.append({**hit, "content": content})

    summary = summarize_content(q.text, enriched)

    payload = {
        "query": q.text,
        "results": raw,
        "summary": summary
    }
    save_research(q.text, payload)
    return payload

@app.get("/history")
async def history():
    return get_research_history()

@app.get("/history/{rid}")
async def history_item(rid: int):
    rec = get_research_by_id(rid)
    if not rec:
        raise HTTPException(404, detail="Not found")
    return rec

@app.get("/")
async def root():
    return {"message": "API is live"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)