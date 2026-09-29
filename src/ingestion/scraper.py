import os
import re
import time
import json
import logging
import pandas as pd
import requests
from bs4 import BeautifulSoup
from googlesearch import search

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def fetch_bbc_links(query: str, num_results: int = 10) -> list[str]:
    """Queries Google to retrieve target BBC article URLs."""
    logging.info(f"Searching for URLs with query: '{query}'")
    urls = []
    try:
        results = search(query, num_results=num_results, sleep_interval=2)
        for url in results:
            if "bbc.com/news" in url or "bbc.co.uk/news" in url:
                urls.append(url)
    except Exception as e:
        logging.error(f"Error gathering URLs from Google: {e}")
    return list(set(urls))

def scrape_bbc_article(url: str) -> dict | None:
    """Scrapes paragraph text, title, and date from a BBC article page."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            logging.warning(f"Failed to fetch {url} (Status: {response.status_code})")
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Extract Headline
        headline_tag = soup.find("h1")
        headline = headline_tag.get_text(strip=True) if headline_tag else ""
        
        # Extract Article Body Paragraphs
        article_body = soup.find("main") or soup
        paragraphs = article_body.find_all("p")
        text_content = " ".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
        
        # Extract Publication Date
        time_tag = soup.find("time")
        pub_date = ""
        if time_tag:
            pub_date = time_tag.get("datetime") or time_tag.get_text(strip=True)
            
        if not text_content:
            logging.warning(f"No body content found for {url}")
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

def run_scraper(queries: list[str], output_raw_path: str = "../../data/raw/articles.csv"):
    """Runs batch scraping pipeline across query lists and exports to raw CSV."""
    # Resolve path if executed from root vs src/ingestion
    if not os.path.exists("../../data") and os.path.exists("data"):
        output_raw_path = "data/raw/articles.csv"

    all_scraped_data = []
    
    for q in queries:
        urls = fetch_bbc_links(q, num_results=10)
        for url in urls:
            logging.info(f"Scraping content from: {url}")
            article_data = scrape_bbc_article(url)
            if article_data:
                all_scraped_data.append(article_data)
            time.sleep(1.5)  # Rate limit safety
            
    df = pd.DataFrame(all_scraped_data)
    os.makedirs(os.path.dirname(output_raw_path), exist_ok=True)
    df.to_csv(output_raw_path, index=False)
    logging.info(f"Scraping complete. Saved {len(df)} articles to '{output_raw_path}'")

if __name__ == "__main__":
    # Test queries targeting conflict phases
    sample_queries = [
        "site:bbc.com/news israel gaza after:2023-10-06 before:2023-11-30",
        "site:bbc.com/news campus protest university Columbia after:2024-04-16 before:2024-05-16"
    ]
    run_scraper(sample_queries)
