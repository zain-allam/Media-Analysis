from __future__ import annotations
import os
import re
import time
import logging
import pandas as pd
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def scrape_bbc_article(url: str) -> dict | None:
    """Scrapes paragraph text, title, and date from an article page."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        headline_tag = soup.find("h1")
        headline = headline_tag.get_text(strip=True) if headline_tag else ""
        
        article_body = soup.find("main") or soup
        paragraphs = article_body.find_all("p")
        text_content = " ".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
        
        time_tag = soup.find("time")
        pub_date = ""
        if time_tag:
            pub_date = time_tag.get("datetime") or time_tag.get_text(strip=True)
            
        if not text_content:
            return None

        return {
            "url": url,
            "headline": headline,
            "date": pub_date,
            "outlet": "BBC News",
            "content": text_content
        }

    except Exception as e:
        logging.error(f"Error scraping article at {url}: {e}")
        return None
