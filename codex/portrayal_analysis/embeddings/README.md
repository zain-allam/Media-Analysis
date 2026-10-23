# Sentence embeddings

Each selected source sentence was encoded independently with sentence-transformers/all-mpnet-base-v2. The vectors are 768-dimensional float32 values normalized to unit length for cosine comparisons. The input was the original sentence, without a party label, portrayal label, or surrounding paragraph appended. No input was truncated.

- sentences_with_embeddings.jsonl: source sentence, original context/labels, and its embedding in one record.
- sentence_embeddings.npy: matrix in the same row order as sentence_metadata.json.
- sentence_metadata.json: sentence IDs, text, labels, source locations and zero-based embedding_row.
- embedding_summary.json: exact cached model revision, hashes, input lengths and array shape.

article_minimum_per_party can filter articles with at least one, two, or three selected sentences for both parties. These embeddings capture semantic information; they do not validate the portrayal labels or guarantee that emotion or political stance can be separated reliably by vector distance alone.
