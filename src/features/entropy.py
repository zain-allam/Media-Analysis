import numpy as np
import pandas as pd
from scipy.stats import entropy
from sklearn.feature_extraction.text import CountVectorizer

def compute_shannon_entropy(texts: list[str], max_features: int = 1000) -> float:
    """Calculates vocabulary entropy H(X) = -sum(P(x) * log2(P(x))) for a list of texts."""
    if not texts:
        return 0.0
        
    cv = CountVectorizer(stop_words='english', max_features=max_features)
    bow_matrix = cv.fit_transform(texts)
    
    word_counts = bow_matrix.sum(axis=0).A1
    if word_counts.sum() == 0:
        return 0.0
        
    word_probs = word_counts / word_counts.sum()
    return float(entropy(word_probs, base=2))

def compute_window_entropy(df: pd.DataFrame) -> pd.DataFrame:
    """Computes Shannon entropy across temporal windows."""
    entropy_results = []
    
    for window, group in df.groupby('window'):
        h_val = compute_shannon_entropy(group['content'].tolist())
        entropy_results.append({
            'window': window,
            'shannon_entropy_bits': h_val,
            'doc_count': len(group)
        })
        
    return pd.DataFrame(entropy_results)
