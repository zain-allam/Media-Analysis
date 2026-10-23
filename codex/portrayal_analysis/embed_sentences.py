"""Embed the selected portrayal sentences using the locally cached MPNet model."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['MPLCONFIGDIR'] = str(ROOT / 'work/matplotlib')

import hashlib
import json
import platform
import numpy as np
from sentence_transformers import SentenceTransformer


def main():
    folder = Path(__file__).resolve().parent
    destination = folder / 'embeddings'
    destination.mkdir(exist_ok=True)
    source = folder / 'portrayal_sentences.jsonl'
    records = [json.loads(line) for line in source.read_text().splitlines()]
    revision = 'e8c3b32edf5434bc2275fc9bab85f82640a19130'
    snapshot = (Path.home() / '.cache/huggingface/hub/'
                'models--sentence-transformers--all-mpnet-base-v2/snapshots' / revision)
    if not snapshot.exists():
        raise FileNotFoundError('This script expects the cached model snapshot: ' + str(snapshot))
    model = SentenceTransformer(str(snapshot), device='cpu')
    texts = [row['sentence'] for row in records]
    lengths = [len(model.tokenizer.encode(text, add_special_tokens=True, truncation=False))
               for text in texts]
    oversized = [row['sentence_id'] for row, length in zip(records, lengths)
                 if length > model.max_seq_length]
    if oversized:
        raise ValueError('These sentences exceed the model limit; split them before embedding: ' + str(oversized))
    print(f'Encoding {len(texts)} sentences; maximum token count {max(lengths)}.', flush=True)
    vectors = model.encode(texts, batch_size=16, show_progress_bar=True,
                           convert_to_numpy=True, normalize_embeddings=True)
    vectors = np.asarray(vectors, dtype=np.float32)
    assert vectors.shape == (len(records), 768)
    assert np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    assert len({row['sentence_id'] for row in records}) == len(records)
    np.save(destination / 'sentence_embeddings.npy', vectors, allow_pickle=False)
    coverage = {row['article_id']: row for row in json.loads((folder / 'article_coverage.json').read_text())}
    metadata = []
    with (destination / 'sentences_with_embeddings.jsonl').open('w') as handle:
        for index, (row, vector, length) in enumerate(zip(records, vectors, lengths)):
            c = coverage[row['article_id']]
            item = dict(row, embedding_row=index, embedding_model='sentence-transformers/all-mpnet-base-v2',
                        embedding_revision=revision, embedding_dimensions=768,
                        embedding_normalized=True, input_token_count=length,
                        article_minimum_per_party=min(c['Palestine_count'], c['Israel_count']))
            metadata.append(item)
            handle.write(json.dumps(dict(item, embedding=vector.tolist()), ensure_ascii=False) + '\n')
    (destination / 'sentence_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    info = dict(model='sentence-transformers/all-mpnet-base-v2', revision=revision,
                input_file=str(source), input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                sentences=len(records), articles=len({r['article_id'] for r in records}),
                shape=list(vectors.shape), dtype=str(vectors.dtype), normalized=True,
                embedding_input='Original sentence only; paragraph context and labels are metadata, not embedded.',
                model_max_sequence_length=model.max_seq_length,
                longest_input_tokens=max(lengths), truncated_inputs=0,
                vector_sha256=hashlib.sha256((destination/'sentence_embeddings.npy').read_bytes()).hexdigest(),
                python=platform.python_version())
    (destination / 'embedding_summary.json').write_text(json.dumps(info, indent=2))
    (destination / 'README.md').write_text('''# Sentence embeddings

Each selected source sentence was encoded independently with sentence-transformers/all-mpnet-base-v2. The vectors are 768-dimensional float32 values normalized to unit length for cosine comparisons. The input was the original sentence, without a party label, portrayal label, or surrounding paragraph appended. No input was truncated.

- sentences_with_embeddings.jsonl: source sentence, original context/labels, and its embedding in one record.
- sentence_embeddings.npy: matrix in the same row order as sentence_metadata.json.
- sentence_metadata.json: sentence IDs, text, labels, source locations and zero-based embedding_row.
- embedding_summary.json: exact cached model revision, hashes, input lengths and array shape.

article_minimum_per_party can filter articles with at least one, two, or three selected sentences for both parties. These embeddings capture semantic information; they do not validate the portrayal labels or guarantee that emotion or political stance can be separated reliably by vector distance alone.
''')
    print(json.dumps(info, indent=2), flush=True)


if __name__ == '__main__':
    main()
