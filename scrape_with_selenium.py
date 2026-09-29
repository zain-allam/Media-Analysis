import os
import re
import time
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def setup_driver():
    options = Options()
    # Run headful (visible browser) or headless with custom User-Agent to pass security checks
    options.add_argument("--headless=new")
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def scrape_articles():
    txt_path = "data/raw/google_doc_corpus.txt"
    output_csv = "data/raw/articles.csv"
    
    if not os.path.exists(txt_path):
        print(f"[!] File not found: {txt_path}")
        return

    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    driver = setup_driver()
    articles = []
    current_outlet = "Unknown"

    print("[+] Launching Browser & Scraping Full Text...\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line in ["New York Times", "Washington Post", "FOX News", "CBS News"]:
            current_outlet = line if line != "FOX News" else "Fox News"
            continue

        if line.startswith("http://") or line.startswith("https://"):
            clean_url = line.split("?")[0]
            
            # Extract date from URL path
            date_match = re.search(r'/(202[3-5])/(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/', clean_url)
            date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else "2024-04-30"

            print(f"Fetching [{current_outlet}]: {clean_url}")
            try:
                driver.get(clean_url)
                time.sleep(3)  # Allow JS and paywall elements to load
                
                soup = BeautifulSoup(driver.page_source, "html.parser")
                paragraphs = soup.find_all("p")
                
                # Filter out short UI text/nav elements
                body_paragraphs = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40]
                content = " ".join(body_paragraphs)

                # Verification check
                if len(content) < 200:
                    print(f"  [!] Warning: Low text length ({len(content)} chars). Likely paywalled.")
                else:
                    print(f"  [✔] Extracted {len(content)} chars.")
                    
            except Exception as e:
                print(f"  [!] Error scraping URL: {e}")
                content = ""

            articles.append({
                "date": date_str,
                "outlet": current_outlet,
                "content": content,
                "url": clean_url
            })

    driver.quit()

    df = pd.DataFrame(articles)
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"\n[✔] Processed {len(df)} articles saved to '{output_csv}'")

if __name__ == "__main__":
    scrape_articles()
