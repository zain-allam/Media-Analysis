import re
import time
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

def get_archive_text(url):
    try:
        # Check Wayback Machine availability API
        api_url = f"http://archive.org/wayback/available?url={url}"
        r = requests.get(api_url, timeout=10).json()
        
        snapshots = r.get("archived_snapshots", {})
        if "closest" in snapshots and snapshots["closest"]["available"]:
            archive_url = snapshots["closest"]["url"]
            print(f"  [➔] Found archive snapshot...")
            
            res = requests.get(archive_url, impersonate="chrome120", timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                paragraphs = soup.find_all("p")
                
                # Filter NYT body paragraphs
                text_blocks = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 35]
                clean_text = " ".join(text_blocks)
                
                if len(clean_text) > 300:
                    return clean_text
    except Exception as e:
        pass
    return None

def main():
    df = pd.read_csv("data/raw/articles.csv")
    updated = 0
    
    print("[+] Extracting full NYT article text via Archive.org snapshots...\n")
    for idx, row in df.iterrows():
        if row["outlet"] == "New York Times":
            print(f"[{idx+1}/{len(df)}] NYT: {row['url'][:60]}...")
            archived_text = get_archive_text(row["url"])
            
            if archived_text:
                df.at[idx, "content"] = archived_text
                updated += 1
                print(f"  [✔] Successfully extracted {len(archived_text)} characters.")
            else:
                print(f"  [!] Archive snapshot not found or incomplete.")
            time.sleep(1)

    df.to_csv("data/raw/articles.csv", index=False)
    print(f"\n[✔] Updated {updated} New York Times articles in data/raw/articles.csv")

if __name__ == "__main__":
    main()
