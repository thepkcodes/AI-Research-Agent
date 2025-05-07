from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import requests
from bs4 import BeautifulSoup
import urllib.parse
from openai import OpenAI
import os
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Research Agent API")

# Allow Next.js at localhost:3000 to talk to us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic models ---
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

# --- DB helpers ---
def init_db():
    conn = sqlite3.connect("research_history.db", check_same_thread=False)
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
    conn = sqlite3.connect("research_history.db", check_same_thread=False)
    cur = conn.cursor()
    ts = datetime.now().isoformat()
    cur.execute(
        "INSERT INTO research_history (query, results, timestamp) VALUES (?, ?, ?)",
        (query, json.dumps(payload), ts)
    )
    conn.commit()
    conn.close()

def get_research_history():
    conn = sqlite3.connect("research_history.db", check_same_thread=False)
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
    conn = sqlite3.connect("research_history.db", check_same_thread=False)
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

# Ensure DB is ready on startup
@app.on_event("startup")
def on_startup():
    init_db()

# --- DuckDuckGo search & parse ---
def search_duckduckgo(query: str, num_results: int = 5):
    q = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={q}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print("DuckDuckGo search error:", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for block in soup.select(".result"):
        a = block.select_one(".result__title a")
        if not a:
            continue
        title = a.get_text(strip=True)
        raw_href = a.get("href", "")
        # DuckDuckGo HTML sometimes uses /l/?uddg=<url>
        if raw_href.startswith("/l/"):
            # extract uddg param
            parsed = urllib.parse.urlparse(raw_href)
            qs = urllib.parse.parse_qs(parsed.query)
            href = qs.get("uddg", [raw_href])[0]
        else:
            href = raw_href
        snippet_el = block.select_one(".result__snippet")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        items.append({"title": title, "url": href, "snippet": snippet})
        if len(items) >= num_results:
            break

    return items

# --- Content extraction ---
def extract_content(url: str, max_length: int = 8000):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        if "text/html" not in r.headers.get("Content-Type", ""):
            return ""
    except Exception as e:
        print("Fetch content error for", url, e)
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

# --- Summarization ---
def summarize_content(query: str, contents: List[dict]):
    system = "You are a research assistant that creates concise, accurate summaries."
    user = f'Query: "{query}"\n\n'
    for i, c in enumerate(contents[:5], start=1):
        excerpt = c.get("content", "")[:800]
        user += (
            f"Article {i}:\n"
            f"Title: {c['title']}\n"
            f"URL: {c['url']}\n\n"
            f"Excerpt: {excerpt}\n\n---\n\n"
        )
    user += "Please provide a concise summary of the key findings in 5–10 bullet points."

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role":"system","content":system}, {"role":"user","content":user}],
            max_tokens=800,
            temperature=0.3
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        # bubble the real error back
        return f"Failed to generate summary: {e}"

# --- Endpoints ---
@app.post("/research", response_model=ResearchResponse)
async def perform_research(q: Query):
    # 1) Search
    raw = search_duckduckgo(q.text, q.num_results)
    if not raw:
        raise HTTPException(status_code=404, detail="No search results found")

    # 2) Extract & enrich
    enriched = []
    for r in raw:
        content = extract_content(r["url"])
        if content:
            enriched.append({**r, "content": content})
    if not enriched:
        raise HTTPException(status_code=500, detail="Content extraction failed")

    # 3) Summarize
    summary = summarize_content(q.text, enriched)

    # 4) Save & respond
    payload = {
        "query": q.text,
        "results": [{"title": e["title"], "url": e["url"], "snippet": e["snippet"]} for e in enriched],
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