from __future__ import annotations
import os
import re
import time
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

# Complete URL dataset parsed directly from your Google Doc
DOC_URLS = [
    # --- NEW YORK TIMES ---
    {"url": "https://www.nytimes.com/2023/04/08/world/middleeast/rockets-lebanon-hamas-hezbollah-israel.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2023/06/14/world/asia/china-mahmoud-abbas-xi-jinping.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2023/09/07/world/middleeast/mahmoud-abbas-video-antisemitic.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2023/10/03/world/middleeast/israeli-herders-west-bank.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2023/12/21/world/middleeast/israel-gaza-bomb-investigation.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/01/27/world/middleeast/gaza-war-israel-hamas-negotiations.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/04/30/us/politics/biden-israel-college-protest.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/05/01/opinion/student-protests-gaza.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/04/30/nyregion/antisemitism-republicans-johnson-college-protests.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/05/01/nyregion/columbia-university-protests-arrests.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/09/07/world/middleeast/american-slain-west-bank-eygi.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/09/19/world/middleeast/saudi-israel-relations.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/10/20/opinion/hamas-colleges-free-speech.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/11/07/opinion/democrats-israel-gaza-war.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2024/11/25/arts/design/nan-goldin-germany-gaza.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2025/04/15/world/middleeast/gaza-medics-autopsies-israel.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2025/04/25/us/politics/trump-student-visa-cancellations.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2025/05/18/us/project-esther-heritage-foundation-palestine.html", "outlet": "New York Times"},
    {"url": "https://www.nytimes.com/2025/04/01/us/israel-gaza-student-protests-canary-mission.html", "outlet": "New York Times"},

    # --- WASHINGTON POST ---
    {"url": "https://www.washingtonpost.com/world/2023/05/11/palestinian-islamic-jihad-gaza-israel/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/world/2023/09/21/gaza-israel-hamas-palestinians-conflict/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/world/2023/02/22/israel-palestinian-violence-timeline/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/world/2024/01/01/israel-hamas-war-gaza-news-palestine/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/world/2023/11/08/israel-war-news-hamas-gaza-palestine/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/dc-md-va/2024/01/13/march-for-gaza-dc-rally-israel-hamas-war/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/nation/2024/01/24/columbia-palestinian-gaza-israel-campus/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/politics/2024/03/18/biden-democrats-protesters-gaza/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2024/04/18/columbia-student-gaza-protests-nypd/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2024/04/23/college-student-antiwar-protests-israel-palestine/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2024/04/23/map-student-protests-arrests-universities-us/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2024/04/23/protests-american-university-israel-gaza-college-campus/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2024/08/30/dc-area-colleges-fall-demonstrations/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2024/09/12/new-college-protest-rules/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2024/10/07/israel-gaza-college-protests-october-7-attacks/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2024/09/04/columbia-university-israel-gaza-student-protests/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2025/04/24/ice-arrest-mahmoud-khalil-no-warrant/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2025/05/07/columbia-university-library-gaza-protest/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/education/2025/05/28/mahmoud-khalil-detention-unconstitutional/", "outlet": "Washington Post"},
    {"url": "https://www.washingtonpost.com/immigration/2025/04/22/mahmoud-khalil-columbia-palestinian-activist-son-birth/", "outlet": "Washington Post"},

    # --- FOX NEWS ---
    {"url": "https://www.foxnews.com/world/israel-deploys-thousands-troops-drones-attack-jenin-stronghold-terrorism-hotspot", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/world/israel-completes-withdrawal-jenin-exchange-rockets-airstrikes", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/world/6-palestinians-killed-latest-clash-against-israel-west-bank-gaza-strip", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/world/israeli-airstrikes-target-gaza-ongoing-protests-no-casualties-reported", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/columbia-student-protesters-stage-walkout-hillary-clintons-class", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/politics/nyc-columbia-university-faculty-students-protest-suspension-far-left-groups", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/politics/anti-israel-protesters-clash-nypd-officers-fiery-scuffle-led-arrests-nypd-burn-hell", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/politics/columbia-suspends-students-anti-israel-event-featuring-speaker-linked-terrorist-organization", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/anti-israel-agitators-light-flares-columbia-university-occupation", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/anti-israel-campus-protesters-make-demand-administrators-vow-stay-put-universities-meet", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/antisemitic-riot-columbia-agitators-take-over-academic-building-barricade-doors", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/colleges-that-once-embraced-anti-israel-protests-now-changing-their-tune-encampments-grow-more-chaotic", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/us-colleges-revise-rules-campuses-brace-more-anti-israel-chaos", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/new-semester-reignites-fears-anti-israel-protests-college-campuses-were-very-concerned", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/masked-anti-israel-protesters-columbia-university-demonstrate-students-check-first-day-classes", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/columbia-anti-israel-agitators-reach-crescendo-intimidation-school-suffers-latest-black-eye", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/columbia-university-threatens-arrest-anti-israel-protesters-remove-encampments-new-demonstrations-loom", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/anti-israel-agitators-take-over-part-columbia-university-library-during-finals-call-liberation-zone", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/mood-flips-columbia-u-after-quashing-latest-protest-trump-pressure-takes-hold", "outlet": "Fox News"},
    {"url": "https://www.foxnews.com/us/anti-israel-protesters-torch-diplomas-outside-columbia-university-graduation-day", "outlet": "Fox News"},

    # --- CBS NEWS ---
    {"url": "https://www.cbsnews.com/news/israel-west-bank-jenin-raid-palestinians-tel-aviv-car-ramming-attack/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/israel-west-bank-raid-jenin-refugee-camp-palestinians-no-water-displaced-un/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/protesters-disrupt-senate-aid-hearing-secretary-of-state-antony-blinken-speaks/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/more-than-30-palestinians-reported-killed-israeli-airstrikes-gaza-strip/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/college-campuses-rattled-israel-hamas-war-60-minutes/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/pittsburgh/news/law-enforcement-agencies-across-the-u-s-step-up-patrols-ahead-of-potential-pro-palestine-rallies/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/pro-palestinian-protests-leave-college-campuses-on-edge-coast-to-coast/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/university-protests-israel-hamas-war-gaza-arrests-campus/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/college-student-protesters-demonstrations-israel-hamas-war-grow/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/college-campus-protests-gaza-israel/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/university-protests-college-campus-israel-hamas-war-police/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/chicago/news/oct-7-chicago-college-protest/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/miami/news/university-of-miami-professor-apologizes-for-violating-university-policy-after-seen-wearing-palestine-sash/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/texas/news/dallas-woman-two-israeli-cousins-killed-hamas-ongoing-anguish/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/chicago/news/students-relieved-uchicago-drops-disciplinary-cases-protest/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/news/columbia-mohsen-mahdawi-trump-administration-you-will-not-silence-me/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/chicago/news/chicago-lawsuit-stopantisemitism-canary-mission-israel-gaza/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/philadelphia/news/elkins-park-synagogue-oct-7-attack-israel/", "outlet": "CBS News"},
    {"url": "https://www.cbsnews.com/newyork/news/hostages-released-israel-hamas-peace-plan-nyc-reaction/", "outlet": "CBS News"}
]

def fetch_article(item: dict) -> dict | None:
    url = item["url"]
    try:
        # Impersonate Chrome browser TLS signatures
        res = requests.get(url, impersonate="chrome120", timeout=15)
        if res.status_code != 200:
            print(f"[BLOCKED {res.status_code}] {url}")
            return None

        soup = BeautifulSoup(res.text, "html.parser")
        
        paragraphs = soup.find_all("p")
        content = " ".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 25])
        
        time_tag = soup.find("time")
        date_str = time_tag.get("datetime") if time_tag else ""
        if date_str:
            date_str = date_str.split("T")[0]
        else:
            match = re.search(r'/(202[3-5])/(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/', url)
            if match:
                date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

        if len(content) < 100 or not date_str:
            print(f"[EMPTY/PAYWALL] {url}")
            return None

        return {
            "date": date_str,
            "outlet": item["outlet"],
            "content": content,
            "url": url
        }
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")
        return None

def main():
    scraped = []
    print(f"[+] Scraping {len(DOC_URLS)} articles with Chrome TLS impersonation...")
    
    for i, item in enumerate(DOC_URLS, 1):
        print(f"[{i}/{len(DOC_URLS)}] Fetching: {item['url']}")
        data = fetch_article(item)
        if data:
            scraped.append(data)
        time.sleep(1)

    df = pd.DataFrame(scraped)
    os.makedirs("data/raw", exist_ok=True)
    df.to_csv("data/raw/articles.csv", index=False)
    print(f"\n[✔] Successfully scraped {len(df)} of {len(DOC_URLS)} articles into 'data/raw/articles.csv'")

if __name__ == "__main__":
    main()
