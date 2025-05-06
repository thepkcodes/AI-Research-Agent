from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import requests
from bs4 import BeautifulSoup
import urllib.parse
import openai
import os
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set OpenAI API key
openai_api_key = os.environ.get("OPENAI_API_KEY")

app = FastAPI(title="Research Agent API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, "*" is okay. In production, use ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def search_duckduckgo(query: str, num_results: int = 5):
    # URL encode the query
    encoded_query = urllib.parse.quote_plus(query)

    # Create the search URL
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    # Set a user agent to avoid blocking
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    # Send the request
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Search request failed: {e}")
        return []
    
    # Parse the HTML
    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract search results
    results = []
    for result in soup.select('.result'):
        # Extract title
        title_element = result.select_one('.result__title')
        if not title_element:
            continue
        title = title_element.get_text().strip()

        # Extract URL
        url_element = result.select_one('.result__url')
        if not url_element:
            continue
        url = url_element.get_text().strip()
        if not url.startswith('http'):
            url = 'https://' + url

        snippet_element = result.select_one('.result__snippet')
        snippet = snippet_element.get_text().strip() if snippet_element else ""

        results.append({
            "title": title,
            "url": url,
            "snippet": snippet
        })

        if len(results) >= num_results:
            break

    return results

def extract_content(url: str, max_length: int = 8000):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64;) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    
    soup = BeautifulSoup(response.text, 'html.parser')

    # Remove script and style elements
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.extract()

    # Get text content
    text = soup.get_text(separator=' ', strip=True)

    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split(" "))
    text = ' '.join(chunk for chunk in chunks if chunk)

    # Truncate if necessary
    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text

def summarize_content(query: str, contents: List[dict]):
    # Create a prompt for the summarization
    prompt = f"""
    Query: "{query}"and

    Here are articles related to this query:

    {'-' * 50}
    """

    for i, content in enumerate(contents):
        prompt += f"""
        Article {i+1}:
        Title: {content['title']}
        URL: {content['url']}

        Content: {content['content'][:1000]}...

        {'-' * 50}
        """

    prompt += """
    Please provide a concise summary of the key findings from these articles related to the query.
    Include the most important points, any consensus among sources, and significant disagreements if they exist.
    Format your response as 5-10 bullet points highlighting the most important information.
    """


    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a research assistant that creates concise, accurate summaries."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in OpenAI API call: {e}")
        return "Failed to generate summary due to an error."
    
def init_db():
    conn = sqlite3.connect('research_history.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS research_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        results TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )
    ''')
    conn.commit()
    conn.close()

def save_research(query: str, results: dict):
    conn = sqlite3.connect('research_history.db')
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO research_history (query, results, timestamp) VALUES (?, ?, ?)",
        (query, json.dumps(results), timestamp)
    )
    conn.commit()
    conn.close()

def get_research_history():
    conn = sqlite3.connect('research_history.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM research_history ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_research_by_id(research_id: int):
    conn = sqlite3.connect('research_history.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM research_history WHERE id = ?", (research_id,))
    row = cursor.fetchall()
    conn.close()
    return dict(row) if row else None

@app.post("/research", response_model=ResearchResponse)
async def perform_research(query: Query):
    try:
        # Step 1: Search DuckDuckGo
        search_results = search_duckduckgo(query.text, query.num_results)

        if not search_results:
            raise HTTPException(status_code=404, detail="No search results found")
        
        # Step 2: Extract content from each result
        enriched_results = []
        for result in search_results:
            content = extract_content(result["url"])
            if content:
                enriched_results.append({
                    "title": result["title"],
                    "url": result["url"],
                    "snippet": result["snippet"],
                    "content": content
                })

        # Step 3: Generate summary with OpenAI
        summary = summarize_content(query.text, enriched_results)

        # Step 4: Format the response
        response_data = {
            "query": query.text,
            "results": [
                {
                    "title": result["title"],
                    "url": result["url"],
                    "snippet": result["snippet"]
                } for result in enriched_results
            ],
            "summary": summary
        }

        # Save to database
        save_research(query.text, response_data)

        return response_data
    
    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

    

@app.get("/history")
async def get_history():
    return get_research_history()

@app.get("/history/{research_id: int}")
async def get_research(research_id: int):
    research = get_research_by_id(research_id)
    if not research:
        raise HTTPException(status_code=404, detail="Research not found")
    return research

@app.get("/")
async def root():
    return {"message": "Research Agent API is running!"}

if __name__ == "__main__":
    init_db()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
