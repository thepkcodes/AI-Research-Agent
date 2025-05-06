from fastapi import FastAPI, HTTPException
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64;) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language":"en-US,en;q=0.5",
        "Referer": "https://www.google.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        content_type = response.headers.get('Content_Type', '').lower()
        if 'text/html' not in content_type:
            print(f"Skipping non-HTML content: {content_type} for URL: {url}")
            return ""
        
    except requests.RequestException as e:
        print(f"Request failed for {url}: {str(e)}")
        return ""
    try:
        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "advertisement", "noscript", "iframe"]):
            element.extract()

        main_content = None
        for container in ["main", "article", ".content", ".post", ".article", ".main-content"]:
            content = soup.select(container)
            if content:
                main_content = content
                break

        if main_content:
            text = " ".join([section.get_text(separator=' ', strip=True) for section in main_content])
        else:
            paragraphs = soup.find_all('p')
            if paragraphs:
                text = " ".join([p.get_text(strip=True) for p in paragraphs])
            else:
                text = soup.get_text(separator=' ', strip=True)

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split(" "))
        text = ' '.join(chunk for chunk in chunks if chunk)

        import re
        text = re.sub(r'\s+', ' ', text).strip()

        # Truncate if necessary
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return text
    
    except Exception as e:
        print(f"Error extracting content from {url}: {str(e)}")
        return ""
    
def summarize_content(query: str, contents: List[dict]):
    # Create a prompt for the summarization
    system_prompt = "You are a research assistant that creates concise, accurate summaries."

    user_prompt = f"""
    Query: "{query}"

    Here are articles related to this query:
    """

    max_articles = min(5, len(contents))

    for i in range(max_articles):
        content = contents[i]
        content_excerpt = content['content'][:800] if 'content' in content else ''

        user_prompt += f"""
        Article {i+1}:
        Title: {content['title']}
        URL: {content['url']}

        Content excerpt: {content_excerpt}

        ---
        """

    user_prompt += """
    Please provide a concise summary of the key findings from these articles related to the query.
    Include the most important points, any consensus among sources, and significant disagreements if they exist.
    Format your response as 5-10 bullet points highlighting the most important information.
    """

    try:
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in OpenAI API call: {str(e)}")
        return f"Failed to generate summary. Error: {str(e)}"
    
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
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

@app.post("/research", response_model=ResearchResponse)
async def perform_research(query: Query):
    try:
        print(f"Processing research query: {query.text}")

        # Step 1: Search DuckDuckGo
        search_results = search_duckduckgo(query.text, query.num_results)
        print(f"Found {len(search_results)} search results")

        if not search_results:
            raise HTTPException(status_code=404, detail="No search results found")
        
        # Step 2: Extract content from each result
        enriched_results = []
        for i, result in enumerate(search_results):
            print(f"Extracting content from result {i+1}: {result['url']}")
            content = extract_content(result["url"])
            content_length = len(content) if content else 0
            print(f"Extracted {content_length} characters from {result['url']}")

            if content:
                enriched_results.append({
                    "title": result["title"],
                    "url": result["url"],
                    "snippet": result["snippet"],
                    "content": content
                })

        if not enriched_results:
            raise HTTPException(status_code=500, detail="Failed to extract content from any search results")

        # Step 3: Generate summary with OpenAI
        print(f"Generating summary for {len(enriched_results)} enriched results")
        summary = summarize_content(query.text, enriched_results)

        if not summary or summary.startswith("Failed to generate summary"):
            print(f"Summary generation failed: {summary}")
            summary = "Failed to generate summary. Please try again otr refine your query."
        else:
            print(f"Successfully generated summary of length {len(summary)}")

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
        try:
            save_research(query.text, response_data)
            print("Research saved to database")
        except Exception as db_error:
            print(f"Failed to save to database: {str(db_error)}")

        return response_data
    
    except HTTPException as he:
        print(f"HTTP exception: {he.detail}")
        raise he

    except Exception as e:
        print(f"Error in research process: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@app.get("/history")
async def get_history():
    return get_research_history()

@app.get("/history/{research_id}")
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
