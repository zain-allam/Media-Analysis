import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests
import time

def scrape_nyt_url(url):
    try:
        # Use Chrome impersonation to bypass basic NYT wall
        res = requests.get(url, impersonate="chrome120", timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # NYT body paragraphs reside inside section[name='articleBody'] or p.ev309250
            paragraphs = soup.find_all("p")
            body_text = " ".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 35])
            
            # Exclude standard NYT paywall boilerplate
            if "log in" not in body_text.lower()[:100] and len(body_text) > 300:
                return body_text
    except Exception:
        pass
    return None

df = pd.read_csv("data/raw/articles.csv")
updated = 0

print("[+] Re-scraping New York Times articles...")
for idx, row in df.iterrows():
    if row["outlet"] == "New York Times":
        text = scrape_nyt_url(row["url"])
        if text:
            df.at[idx, "content"] = text
            updated += 1
            print(f"  [✔] Scraped NYT ({len(text)} chars): {row['url'][:60]}...")
        else:
            print(f"  [!] Blocked by paywall: {row['url'][:60]}...")
        time.sleep(0.5)

df.to_csv("data/raw/articles.csv", index=False)
print(f"\n[✔] Updated {updated} NYT articles in data/raw/articles.csv")
