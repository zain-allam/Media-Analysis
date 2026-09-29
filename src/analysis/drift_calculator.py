import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_distances

class EmbeddingEngine:
    def __init__(self, model_name: str = "sentence-transformers/all-mpnet-base-v2"):
        self.model = SentenceTransformer(model_name)

    def generate_embeddings(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, show_progress_bar=False)

def calculate_window_centroids_and_drift(df: pd.DataFrame, model_name: str) -> pd.DataFrame:
    """Generates centroids per window and computes Cosine Distance against W1 baseline."""
    engine = EmbeddingEngine(model_name)
    
    w1_texts = df[df['window'] == 'W1']['content'].tolist()
    w1_embeddings = engine.generate_embeddings(w1_texts)
    baseline_centroid = np.mean(w1_embeddings, axis=0).reshape(1, -1)
    
    drift_results = []
    for window, group in df.groupby('window'):
        window_texts = group['content'].tolist()
        window_embeds = engine.generate_embeddings(window_texts)
        window_centroid = np.mean(window_embeds, axis=0).reshape(1, -1)
        
        dist = cosine_distances(baseline_centroid, window_centroid)[0][0]
        drift_results.append({
            'window': window,
            'cosine_drift': float(dist)
        })
        
    return pd.DataFrame(drift_results)
