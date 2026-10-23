"""Collect subscriber articles using a dedicated, manually authenticated browser.

Run from the Media-Analysis project directory. Output is a separate review CSV.
Credentials are entered only in the publisher's browser pages.
"""
import argparse
import csv
import json
import re
import time
from datetime import date
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


SELECTORS = {
    "New York Times": 'section[name="articleBody"]',
    "Washington Post": '.article-body, [data-qa="article-body"]',
    "Fox News": '.article-body',
    "CBS News": '.content__body, .article__body',
}
FIELDS = ['date', 'outlet', 'content', 'url', 'status', 'error', 'candidate_content']


def read_urls(path):
    outlet = 'Unknown'
    seen = set()
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line in (*SELECTORS, 'FOX News'):
            outlet = 'Fox News' if line == 'FOX News' else line
        elif line.startswith(('https://', 'http://')) and line not in seen:
            seen.add(line)
            yield outlet, line


def extract(driver, outlet):
    # Visible paragraphs only; never fall back to every paragraph on the page.
    selector = SELECTORS.get(outlet, 'article')
    candidates = []
    for body in driver.find_elements(By.CSS_SELECTOR, selector):
        if body.is_displayed():
            paragraphs = []
            for p in body.find_elements(By.TAG_NAME, 'p'):
                text = p.text.strip()
                if not p.is_displayed() or not text or text in {'In:', 'Advertisement', 'SKIP ADVERTISEMENT'}:
                    continue
                # Exclude page components by their DOM ancestry, not article sentiment.
                if driver.execute_script('return !!arguments[0].closest(arguments[1])', p,
                        'figure, figcaption, .caption, .video-container, .video-player, '
                        '.author-bio, .author-bio-container, .related-content, .newsletter'):
                    continue
                if outlet == 'Fox News' and re.match(
                        r"^(Anders Hagstrom|Timothy Nerozzi) is (a reporter|a writer) (with|for) Fox News", text):
                    continue
                paragraphs.append(text)
            candidates.append('\n\n'.join(paragraphs))
    return max(candidates, key=len, default='')


def publication_date(driver, url):
    values = []
    for element in driver.find_elements(By.CSS_SELECTOR,
            'meta[property="article:published_time"], meta[itemprop="datePublished"], '
            'meta[name="dc.date"], meta[name="date"], time[itemprop="datePublished"]'):
        values.append(element.get_attribute('content') or element.get_attribute('datetime') or '')
    def article_dates(value):
        if isinstance(value, list):
            for item in value:
                yield from article_dates(item)
        elif isinstance(value, dict):
            types = value.get('@type', [])
            types = [types] if isinstance(types, str) else types
            if any(t in {'NewsArticle', 'Article', 'ReportageNewsArticle'} for t in types):
                yield value.get('datePublished', '')
            for item in value.values():
                if isinstance(item, (dict, list)):
                    yield from article_dates(item)
    for element in driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]'):
        try:
            values.extend(article_dates(json.loads(element.get_attribute('textContent') or '{}')))
        except (ValueError, TypeError):
            continue
    for value in values:
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except (ValueError, TypeError):
            pass
    match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('data/raw/google_doc_corpus.txt'))
    parser.add_argument('--output', type=Path, default=Path('data/raw/articles_authenticated_review.csv'))
    parser.add_argument('--profile', type=Path,
                        default=Path.home() / 'Library/Application Support/Media-Analysis/Selenium')
    args = parser.parse_args()
    items = list(read_urls(args.input))
    if not items:
        parser.error('No article URLs found in input.')
    if args.output.exists():
        parser.error('Output already exists; choose another --output to preserve your previous run.')
    args.profile.mkdir(parents=True, exist_ok=True)
    options = webdriver.ChromeOptions()
    options.add_argument(f'--user-data-dir={args.profile.resolve()}')
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    try:
        for outlet, home in [('New York Times', 'https://www.nytimes.com/'),
                             ('Washington Post', 'https://www.washingtonpost.com/')]:
            if any(name == outlet for name, _ in items):
                driver.get(home)
                input(f'Log in to {outlet} in this browser, then press Enter here. ')

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for outlet, url in items:
                row = dict(date='', outlet=outlet, content='', url=url,
                           status='needs_review', error='', candidate_content='')
                print(f'\n[{outlet}] {url}')
                try:
                    driver.get(url)
                    WebDriverWait(driver, 30).until(
                        lambda d: d.execute_script('return document.readyState') == 'complete')
                    input('Check this article in the browser. Sign in if needed, then press Enter. ')
                    content = extract(driver, outlet)
                    row['candidate_content'] = content
                    row['date'] = publication_date(driver, url)
                    preview = args.output.parent / (args.output.stem + '_preview.txt')
                    preview.write_text(url + '\n\n' + content, encoding='utf-8')
                    print(f'Extracted {len(content)} characters.')
                    print(f'Publication date: {row["date"] or "MISSING — requires review"}')
                    print(f'Full extracted text for review: {preview.resolve()}')
                    print(content[:350] or '[No article body found]')
                    print('\nLast 350 characters:\n' + content[-350:])
                    if content:
                        answer = input('Does the extracted text match the complete article body? [y/N] ')
                        if answer.strip().lower() == 'y':
                            if row['date']:
                                row.update(content=content, status='verified')
                            else:
                                row['status'] = 'needs_date'
                except Exception as exc:
                    row.update(status='error', error=f'{type(exc).__name__}: {exc}')
                    print(row['error'])
                writer.writerow(row)
                handle.flush()
                time.sleep(2)
    finally:
        driver.quit()
    print(f'Written to {args.output}. Only verified rows contain analysis text.')


if __name__ == '__main__':
    main()
