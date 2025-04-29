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

        result.append({
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