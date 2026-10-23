# Media article sentence data and feature extraction

This package contains 231 selected sentences from 30 articles, grouped into Palestine-related and Israel-related portrayals. The original collection attempted 78 URLs; the remaining 48 articles were inaccessible, required extraction review, or were outside the configured date windows. Their coverage records are included.

## Read the saved data

- **classified_sentences.xlsx**: an Excel workbook. Articles shows coverage and counts for all 78 URLs; Sentences contains the 231 selected sentences and their labels. Filter Article ID and Party group to read one article at a time. Blank article counts mean unavailable, not zero relevant sentences.
- **classified_sentences_by_article.txt**: the full selected sentences grouped by article, then Palestine/Israel, with their targets, voices and sources. Opens in a text editor.
- **classified_sentences.csv**: one selected sentence per row, including labels, source locations and text features. Opens in Excel or pandas. Embeddings are stored separately so the table remains readable.
- **classified_sentences_report.html**: the interactive article report. Open it in a browser.
- **data/classified_sentences.jsonl**: complete machine-readable records, with original paragraph context and source hashes. One JSON object per line.
- **data/article_coverage.json**: counts/status for every requested URL.
- **precomputed_features/**: already calculated embeddings, matching metadata, features CSV, readable report and run summary. The matrix has shape `(231, 768)`.

## Run feature extraction

In Terminal, change to the folder containing this README and run:

```bash
python3 -m pip install -r requirements.txt
python3 extract_features.py
```

The supplied sentence data is selected automatically as the default input. Outputs are saved in `features/`. The first run may download the model if it is not cached. The model revision is pinned in the script for reproducibility. `--offline` requires a previously cached model. No API key is needed.

To choose a different output folder:

```bash
python3 extract_features.py --output my_features
```

To replace outputs from a previous run, add `--overwrite`. The script otherwise refuses a nonempty output folder.

## Select an article subset

Minimum means selected sentences for **each party within the same article**:

| Option | Articles in this dataset |
| --- | ---: |
| Default / `--min-per-party 0` | 30 |
| `--min-per-party 1` | 24 |
| `--min-per-party 2` | 20 |
| `--min-per-party 3` | 15 |

For example:

```bash
python3 extract_features.py --min-per-party 2 --output features_min2
```

To export the classified data and counts without loading the transformer:

```bash
python3 extract_features.py --export-only --output labels_only
```

To use another already-labeled CSV, JSON array, or JSONL file:

```bash
python3 extract_features.py --input my_classified_sentences.jsonl --output my_features
```

Each record must contain unique `sentence_id`, nonempty `article_id` and `sentence`, and a `category` of `Palestine` or `Israel`. Other label/source fields are preserved. Cohort counts are calculated from the supplied sentence sample, not from unselected article text.

## Features produced

- `sentence_embeddings.npy`: float32 matrix, one row per selected sentence and 768 columns. Rows are normalized to unit length for cosine similarity.
- `sentence_metadata.jsonl`: source sentence and labels plus zero-based `embedding_row`, token/word/character counts and cohort metadata.
- `sentence_features.csv`: readable version of the metadata and scalar features.
- `sentences_with_embeddings.jsonl`: metadata and vector together in each record.
- `article_counts.csv`: selected sentence counts for each group by article.
- `classified_sentences_by_article.txt`: readable article-by-article export.
- `run_summary.json`: model revision, counts, dimensions and file hashes.

Input to the model is the original sentence only. The party label and paragraph context are not appended to the text. Sentence context remains available as metadata for interpretation. If a sentence exceeds the model token limit, the script stops rather than silently truncating it.

## Load the matrix in Python

```python
import json
import numpy as np

vectors = np.load("features/sentence_embeddings.npy", allow_pickle=False)
with open("features/sentence_metadata.jsonl", encoding="utf-8") as f:
    sentences = [json.loads(line) for line in f if line.strip()]

index = 0
print(sentences[index]["sentence_id"])
print(sentences[index]["category"])
print(sentences[index]["sentence"])
print(vectors[index].shape)  # (768,)

# Vectors are normalized, so their dot product is cosine similarity.
similarity = float(vectors[0] @ vectors[1])
print(similarity)
```

## Meaning of the classifications

The saved annotations describe a sentence's primary portrayal target. They include facts, narrator framing and attributed statements. Each record distinguishes the exact target, target type, source/voice and portrayal (`favorable`, `critical`, `mixed`, `neutral`). Explicitly pro-Palestinian/pro-Israel movements are included with their exact targets identified. They do not stand for entire populations, and Jewish identity alone is not treated as pro-Israel affiliation.

Neutral means no explicit approval/disapproval of the target, not absence of suffering. Quoting a source does not imply author endorsement, and an allegation is not independently verified by this dataset. Some short sentences need the saved paragraph context to identify their speaker or referent.

The annotations were proposed through contextual LLM review and purposefully sampled at up to five sentences per article per party. They are not exhaustive labels for every sentence in each article and have not been independently validated. Sentences principally about neither or inseparably both sides were not selected.

**The code loads these saved classifications; it does not generate political labels for new articles.** It reproduces the transformer embeddings and text features. Embedding dimensions are learned numerical features, not separately named emotion or bias scores.

## Verified environment

The full feature-extraction run was checked on Python 3.9.6 with NumPy 2.0.2, sentence-transformers 5.1.2, torch 2.8.0 and transformers 4.57.6. All 231 sentences fit the model input limit, and the generated normalized matrix matched the earlier saved embeddings. Reproducing every floating-point value may depend on package versions and device.
