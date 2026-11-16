"""Compute publisher-specific W1-W5 similarity from saved sentence embeddings.

No model download or re-embedding is needed. Requires NumPy.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', type=Path, default=Path(__file__).resolve().parent / 'features')
    parser.add_argument('--publisher', default='CBS News')
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()

    vectors = np.load(args.features / 'sentence_embeddings.npy', allow_pickle=False)
    records = [json.loads(line) for line in (args.features / 'sentence_metadata.jsonl').read_text().splitlines() if line.strip()]
    if vectors.ndim != 2 or not np.isfinite(vectors).all():
        raise ValueError('Embeddings must be a finite, two-dimensional matrix.')
    indices = [r['embedding_row'] for r in records]
    if sorted(indices) != list(range(len(vectors))):
        raise ValueError('Metadata embedding_row values must match every embedding row exactly once.')

    windows = [f'W{i}' for i in range(1, 6)]
    matrices = {}
    counts = []
    for window in windows:
        selected = [r for r in records if r['outlet'] == args.publisher and r['window'] == window]
        if not selected:
            raise ValueError(f'No embeddings for {args.publisher}, {window}. Cannot produce a complete 5x5 matrix.')
        matrices[window] = vectors[[r['embedding_row'] for r in selected]]
        counts.append((window, len(selected), len({r['article_id'] for r in selected})))

    # Each sentence has equal weight, including across different articles.
    centroids = np.stack([matrices[w].mean(axis=0, dtype=np.float64) for w in windows])
    norms = np.linalg.norm(centroids, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError('Cosine similarity is undefined for a zero mean vector.')
    unit_centroids = centroids / norms
    similarity = np.clip(unit_centroids @ unit_centroids.T, -1.0, 1.0)
    np.fill_diagonal(similarity, 1.0)

    output = args.output or args.features.parent / 'similarity' / args.publisher.lower().replace(' ', '_')
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'cosine_similarity.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Window', *windows])
        writer.writerows([window, *row] for window, row in zip(windows, similarity))
    with (output / 'window_counts.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Window', 'Sentences', 'Articles'])
        writer.writerows(counts)
    np.save(output / 'window_centroids.npy', centroids, allow_pickle=False)
    np.save(output / 'cosine_similarity.npy', similarity, allow_pickle=False)
    np.savez_compressed(output / 'window_matrices.npz', **matrices)

    print(f'\n{args.publisher}: cosine similarity of mean sentence vectors')
    print('       ' + ''.join(f'{w:>9}' for w in windows))
    for window, row in zip(windows, similarity):
        print(f'{window:<7}' + ''.join(f'{value:9.4f}' for value in row))
    print(f'\nSaved results to: {output.resolve()}')


if __name__ == '__main__':
    main()
