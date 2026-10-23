#!/usr/bin/env python3
"""Export reviewed sentence labels and extract MPNet embeddings and text features.

Run `python3 extract_features.py --help` for examples/options. The supplied labels
are saved contextual annotations; this script does not classify unseen text.
"""
import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
MODEL = 'sentence-transformers/all-mpnet-base-v2'
REVISION = 'e8c3b32edf5434bc2275fc9bab85f82640a19130'
CSV_FIELDS = [
    'article_id', 'article_title', 'outlet', 'date', 'window',
    'category', 'sentence_id', 'sentence', 'voice', 'source_speaker',
    'portrayal', 'target_type', 'target_entity', 'frame',
    'paragraph_number', 'sentence_in_paragraph', 'url',
    'article_minimum_per_party', 'word_count', 'character_count',
    'model_token_count', 'embedding_row', 'embedding_dimensions',
    'embedding_normalized', 'embedding_model',
]


def load_records(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        if path.suffix.lower() == '.csv':
            records = list(csv.DictReader(handle))
        elif path.suffix.lower() == '.json':
            records = json.load(handle)
        else:
            records = [json.loads(line) for line in handle if line.strip()]
    if not isinstance(records, list) or not records:
        raise ValueError('Input must contain at least one sentence record.')
    seen = set()
    for index, row in enumerate(records, 1):
        for key in ['article_id', 'sentence_id', 'sentence', 'category']:
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f'Record {index}: missing or empty {key}.')
        if row['category'] not in {'Palestine', 'Israel'}:
            raise ValueError(f"Record {index}: category must be Palestine or Israel.")
        if row['sentence_id'] in seen:
            raise ValueError(f"Duplicate sentence_id: {row['sentence_id']}")
        seen.add(row['sentence_id'])
    return records


def select_cohort(records, minimum):
    counts = Counter((r['article_id'], r['category']) for r in records)
    selected = []
    for original in records:
        row = dict(original)
        row['article_minimum_per_party'] = min(
            counts[(row['article_id'], 'Palestine')],
            counts[(row['article_id'], 'Israel')])
        if row['article_minimum_per_party'] >= minimum:
            row['word_count'] = len(re.findall(r"\b\w+(?:[’'-]\w+)*\b", row['sentence']))
            row['character_count'] = len(row['sentence'])
            selected.append(row)
    if not selected:
        raise ValueError(f'No articles have at least {minimum} sentences per party.')
    return selected


def write_jsonl(path, rows):
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def write_exports(folder, rows):
    with (folder / 'sentence_features.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter((r['article_id'], r['category']) for r in rows)
    articles = {}
    for row in rows:
        articles.setdefault(row['article_id'], row)
    with (folder / 'article_counts.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        fields = ['article_id', 'article_title', 'outlet', 'date', 'Palestine_count', 'Israel_count', 'url']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for aid, row in articles.items():
            writer.writerow(dict(article_id=aid, article_title=row.get('article_title', ''),
                outlet=row.get('outlet', ''), date=row.get('date', ''),
                Palestine_count=counts[(aid, 'Palestine')],
                Israel_count=counts[(aid, 'Israel')], url=row.get('url', '')))
    lines = ['CLASSIFIED SENTENCES BY ARTICLE',
             'Labels describe portrayal, not necessarily the author\'s personal views.',
             'Neutral means no explicit approval/disapproval of the target. It does not mean no suffering.', '']
    for aid, article in articles.items():
        lines.extend(['=' * 80, f"{aid}: {article.get('article_title', '')}",
            f"{article.get('outlet', '')} | {article.get('date', '')}",
            article.get('url', ''), ''])
        for side in ['Palestine', 'Israel']:
            group = [r for r in rows if r['article_id'] == aid and r['category'] == side]
            lines.extend([f'{side.upper()} — {len(group)} selected sentence(s)', '-' * 60])
            if not group:
                lines.append('No sentence selected for this group.')
            for row in group:
                lines.extend([f"{row['sentence_id']}: {row['sentence']}",
                    f"  Portrayal: {row.get('portrayal', '')}; voice: {row.get('voice', '')}",
                    f"  Source: {row.get('source_speaker') or 'Narrator'}",
                    f"  Target: {row.get('target_entity', '')} ({row.get('target_type', '')})",
                    f"  Frame: {row.get('frame', '')}", ''])
            lines.append('')
    (folder / 'classified_sentences_by_article.txt').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=BASE / 'data/classified_sentences.jsonl',
                        help='Labeled sentences in JSONL, JSON array, or CSV format.')
    parser.add_argument('--output', type=Path, default=BASE / 'features')
    parser.add_argument('--min-per-party', type=int, choices=range(0, 6), default=0,
                        help='Keep only articles with at least this many sentences for EACH party. 0 keeps all.')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--device', default='cpu', help='cpu, mps, or cuda if supported by your installation.')
    parser.add_argument('--model-path', type=Path, help='Optional local all-mpnet-base-v2 folder instead of the Hub model name.')
    parser.add_argument('--offline', action='store_true', help='Use cached/local model files only.')
    parser.add_argument('--export-only', action='store_true', help='Export labels, text, and counts without loading a model.')
    parser.add_argument('--overwrite', action='store_true', help='Replace known output files from a previous run.')
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error('--batch-size must be positive.')
    records = select_cohort(load_records(args.input), args.min_per_party)
    if args.output.exists() and any(args.output.iterdir()) and not args.overwrite:
        parser.error('Output directory is not empty. Choose another --output or use --overwrite.')
    args.output.mkdir(parents=True, exist_ok=True)
    info = dict(input_file=str(args.input.resolve()),
                input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                sentences=len(records), articles=len({r['article_id'] for r in records}),
                minimum_per_party=args.min_per_party,
                by_party=dict(Counter(r['category'] for r in records)),
                classification_labels='Loaded from input; not generated by this script.',
                embedding_input='Original sentence only. Context and classification labels remain metadata.',
                model=None, dimensions=None)
    if not args.export_only:
        if args.offline:
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
        import numpy as np
        from sentence_transformers import SentenceTransformer
        kwargs = dict(device=args.device)
        if args.model_path is None:
            kwargs['revision'] = REVISION
        model = SentenceTransformer(str(args.model_path) if args.model_path else MODEL, **kwargs)
        lengths = [len(model.tokenizer.encode(r['sentence'], add_special_tokens=True, truncation=False)) for r in records]
        too_long = [r['sentence_id'] for r, count in zip(records, lengths) if count > model.max_seq_length]
        if too_long:
            raise ValueError('Input exceeds the model token limit; split these sentences before embedding: ' + ', '.join(too_long))
        print(f'Embedding {len(records)} sentences from {info["articles"]} articles...', flush=True)
        vectors = np.asarray(model.encode([r['sentence'] for r in records],
            batch_size=args.batch_size, show_progress_bar=True, normalize_embeddings=True,
            convert_to_numpy=True), dtype=np.float32)
        if vectors.shape != (len(records), 768) or not np.isfinite(vectors).all():
            raise ValueError(f'Unexpected embedding output: {vectors.shape}. Expected finite 768-dimensional vectors.')
        if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5):
            raise ValueError('Embedding vectors are not normalized.')
        np.save(args.output / 'sentence_embeddings.npy', vectors, allow_pickle=False)
        enriched = []
        for index, (row, count, vector) in enumerate(zip(records, lengths, vectors)):
            row.update(embedding_row=index, model_token_count=count, embedding_dimensions=768,
                embedding_normalized=True, embedding_model=MODEL)
            enriched.append(dict(row, embedding=vector.tolist()))
        write_jsonl(args.output / 'sentences_with_embeddings.jsonl', enriched)
        info.update(model=MODEL, model_revision=REVISION if args.model_path is None else None,
            model_source=str(args.model_path.resolve()) if args.model_path else MODEL,
            dimensions=768, normalized=True,
            max_input_tokens=max(lengths), model_token_limit=model.max_seq_length, truncated_inputs=0,
            embedding_sha256=hashlib.sha256((args.output / 'sentence_embeddings.npy').read_bytes()).hexdigest())
    elif args.overwrite:
        # An export-only rerun must not leave an old embedding matrix that no
        # longer matches the new rows. Only remove files owned by this script.
        for filename in ['sentence_embeddings.npy', 'sentences_with_embeddings.jsonl']:
            path = args.output / filename
            if path.exists():
                path.unlink()
    write_jsonl(args.output / 'sentence_metadata.jsonl', records)
    write_exports(args.output, records)
    (args.output / 'run_summary.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    print(json.dumps(info, indent=2))
    print('Saved to:', args.output.resolve())


if __name__ == '__main__':
    main()
