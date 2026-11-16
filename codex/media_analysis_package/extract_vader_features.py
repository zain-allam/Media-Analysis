"""Extract sentence-level VADER labels and their proportions for CBS and Fox.

Input: CSV with outlet, window, content; optional article_id, url, date.
Use clean article body text with original capitalization and punctuation.
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

LABELS = ['negative', 'neutral', 'positive']
PUBLISHERS = ['CBS News', 'Fox News']
WINDOWS = ['W1', 'W2', 'W3', 'W4', 'W5']


def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize(counts):
    total = sum(counts.values())
    return dict(sentences=total, **{f'{label}_count': counts[label] for label in LABELS},
                **{f'{label}_proportion': counts[label] / total if total else None for label in LABELS})


def main():
    import numpy as np
    from nltk.tokenize import sent_tokenize
    from scipy.spatial.distance import jensenshannon
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('vader_results'))
    args = parser.parse_args()
    with args.input.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not {'outlet', 'window', 'content'} <= set(reader.fieldnames or []):
            raise ValueError('Input CSV needs outlet, window, and content columns.')
        articles = list(reader)

    analyzer = SentimentIntensityAnalyzer()
    sentence_rows, article_rows, issues = [], [], []
    group_counts = defaultdict(Counter)
    group_articles = Counter()
    seen = set()
    for source_row, article in enumerate(articles, start=2):
        publisher = article['outlet'].strip()
        if publisher not in PUBLISHERS:
            continue
        window = article['window'].strip()
        article_id = article.get('article_id') or f'csv_row_{source_row}'
        url = article.get('url', '').strip()
        text = article['content'].strip()
        key = (publisher, url or article_id)
        if key in seen:
            raise ValueError(f'Duplicate article at CSV row {source_row}: {key}')
        seen.add(key)
        if window not in WINDOWS:
            raise ValueError(f'Unexpected window {window!r} at row {source_row}.')
        common = dict(article_id=article_id, publisher=publisher, window=window,
                      url=url, date=article.get('date', ''))
        if not text:
            issues.append(dict(article_id=article_id, issue='Empty content; excluded'))
            article_rows.append(dict(**common, status='Empty content', **summarize(Counter())))
            continue
        if text == text.lower() and any(c.isalpha() for c in text):
            issues.append(dict(article_id=article_id, issue='All lowercase: VADER capitalization emphasis was lost'))
        if any(s in text.lower() for s in ['all rights reserved', 'quotes displayed in real-time', 'skip to content']):
            issues.append(dict(article_id=article_id, issue='Possible site boilerplate: review article body before analysis'))
        try:
            sentences = sent_tokenize(text, language='english')
        except LookupError as exc:
            raise SystemExit('Install sentence tokenizer first: python3 -m nltk.downloader punkt_tab') from exc
        counts = Counter()
        for number, sentence in enumerate(sentences, start=1):
            scores = analyzer.polarity_scores(sentence)
            compound = scores['compound']
            label = 'negative' if compound <= -0.05 else 'positive' if compound >= 0.05 else 'neutral'
            counts[label] += 1
            sentence_rows.append(dict(**common, sentence_number=number, sentence=sentence,
                                      compound=compound, sentiment=label,
                                      vader_neg=scores['neg'], vader_neu=scores['neu'], vader_pos=scores['pos']))
        article_rows.append(dict(**common, status='Scored', **summarize(counts)))
        group_counts[publisher, window].update(counts)
        group_articles[publisher, window] += 1

    args.output.mkdir(parents=True, exist_ok=True)
    common_fields = ['article_id', 'publisher', 'window', 'url', 'date']
    summary_fields = ['sentences'] + [f'{s}_count' for s in LABELS] + [f'{s}_proportion' for s in LABELS]
    write_csv(args.output / 'sentence_sentiment.csv', common_fields + ['sentence_number', 'sentence', 'compound', 'sentiment', 'vader_neg', 'vader_neu', 'vader_pos'], sentence_rows)
    write_csv(args.output / 'article_sentiment_proportions.csv', common_fields + ['status'] + summary_fields, article_rows)
    groups = []
    for publisher in PUBLISHERS:
        for window in WINDOWS:
            counts = group_counts[publisher, window]
            groups.append(dict(publisher=publisher, window=window,
                               status='Available' if sum(counts.values()) else 'Missing data',
                               articles=group_articles[publisher, window], **summarize(counts)))
        matrix_rows = []
        for a in WINDOWS:
            row = {'Window': a}
            for b in WINDOWS:
                ca, cb = group_counts[publisher, a], group_counts[publisher, b]
                if not sum(ca.values()) or not sum(cb.values()):
                    row[b] = None  # Missing data is not zero distance.
                else:
                    pa = np.array([ca[s] for s in LABELS], dtype=float) / sum(ca.values())
                    pb = np.array([cb[s] for s in LABELS], dtype=float) / sum(cb.values())
                    row[b] = float(jensenshannon(pa, pb, base=2))
            matrix_rows.append(row)
        slug = publisher.lower().replace(' ', '_')
        write_csv(args.output / f'{slug}_distance_matrix.csv', ['Window'] + WINDOWS, matrix_rows)
    write_csv(args.output / 'publisher_window_proportions.csv', ['publisher', 'window', 'status', 'articles'] + summary_fields, groups)
    write_csv(args.output / 'input_review.csv', ['article_id', 'issue'], issues)
    (args.output / 'METHOD.txt').write_text(
        'Sentence labels: compound <= -0.05 negative; >= 0.05 positive; otherwise neutral.\n'
        'Discrete proportions count sentence labels; they are NOT averages of VADER neg/neu/pos scores.\n'
        'Window aggregation pools sentences, so longer articles receive greater weight.\n'
        'Distances: Jensen-Shannon, base 2, range 0 to 1. Blank cells mean missing data.\n'
        'Sentiment is not target-specific political stance or author opinion.\n'
        f'Input: {args.input.resolve()}\n', encoding='utf-8')
    print(f'Scored {len(article_rows)} CBS/Fox records and {len(sentence_rows)} sentences.')
    print(f'Input review flags: {len(issues)}. Results: {args.output.resolve()}')


if __name__ == '__main__':
    main()
