import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT = Path(__file__).resolve().parent
FEATURES = ROOT / "features"
OUTPUT = ROOT / "vader_results"
PUBLISHER = "CBS News"
WINDOWS = ["W1", "W2", "W3", "W4", "W5"]

OUTPUT.mkdir(exist_ok=True)

records = [
    json.loads(line)
    for line in (FEATURES / "sentence_metadata.jsonl")
    .read_text().splitlines()
    if line.strip()
]

analyzer = SentimentIntensityAnalyzer()
rows = []

for record in records:
    if record["outlet"] != PUBLISHER:
        continue

    compound = analyzer.polarity_scores(
        record["sentence"]
    )["compound"]

    if compound <= -0.05:
        label = "negative"
    elif compound >= 0.05:
        label = "positive"
    else:
        label = "neutral"

    rows.append({
        "sentence_id": record["sentence_id"],
        "article_id": record["article_id"],
        "window": record["window"],
        "publisher": record["outlet"],
        "party": record["category"],
        "sentence": record["sentence"],
        "compound": compound,
        "sentiment": label,
    })

df = pd.DataFrame(rows)
if df.empty:
    raise ValueError(f"No saved sentences for {PUBLISHER}")

counts = pd.crosstab(df["window"], df["sentiment"]).reindex(
    index=WINDOWS,
    columns=["negative", "neutral", "positive"],
    fill_value=0,
)

missing = counts.index[counts.sum(axis=1) == 0].tolist()
if missing:
    raise ValueError(f"Missing sentences for windows: {missing}")

# Each sentence has equal weight.
proportions = counts.div(counts.sum(axis=1), axis=0)

# Compare every window with every other window.
distance = np.array([
    [
        jensenshannon(
            proportions.loc[a].to_numpy(),
            proportions.loc[b].to_numpy(),
            base=2,
        )
        for b in WINDOWS
    ]
    for a in WINDOWS
])

matrix = pd.DataFrame(
    distance, index=WINDOWS, columns=WINDOWS
)
matrix.index.name = "Window"

df.to_csv(OUTPUT / "sentence_sentiment.csv", index=False)
counts.to_csv(OUTPUT / "sentiment_counts.csv")
proportions.to_csv(OUTPUT / "sentiment_proportions.csv")
matrix.to_csv(OUTPUT / "vader_distance_matrix.csv")

print("\nSentiment proportions:")
print(proportions.round(4))
print("\nJensen–Shannon distance:")
print(matrix.round(4))