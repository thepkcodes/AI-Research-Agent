from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import requests
from bs4 import BeautifulSoup
import openai
import os
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()