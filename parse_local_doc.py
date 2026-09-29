import os
import re
import pandas as pd

def parse_txt_to_csv(txt_path="data/raw/google_doc_corpus.txt", output_csv="data/raw/articles.csv"):
    if not os.path.exists(txt_path):
        print(f"[!] Error: File '{txt_path}' not found.")
        return

    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    articles = []
    current_outlet = "Unknown"

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line in ["New York Times", "Washington Post", "FOX News", "CBS News"]:
            current_outlet = line if line != "FOX News" else "Fox News"
            continue

        if line.startswith("http://") or line.startswith("https://"):
            url = line.split("?")[0]
            
            date_match = re.search(r'/(202[3-5])/(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/', url)
            date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else "2024-04-30"

            articles.append({
                "date": date_str,
                "outlet": current_outlet,
                "content": f"Article from {current_outlet} covering events on {date_str}. URL: {url}",
                "url": url
            })

    df = pd.DataFrame(articles)
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"[✔] Successfully processed {len(df)} articles into '{output_csv}'")

if __name__ == "__main__":
    parse_txt_to_csv()
