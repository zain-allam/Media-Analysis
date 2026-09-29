import yaml
import pandas as pd
from src.features.entropy import compute_window_entropy
from src.analysis.drift_calculator import calculate_window_centroids_and_drift

def main():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
        
    print("[+] Loading processed article corpus...")
    df = pd.read_csv("data/processed/articles_cleaned.csv")
    
    print("[+] Executing Layer B: Shannon Entropy Calculations...")
    entropy_df = compute_window_entropy(df)
    
    print("[+] Executing Layer C: Transformer Vector Drift...")
    drift_df = calculate_window_centroids_and_drift(
        df, model_name=config['models']['embedding_model']
    )
    
    profile = entropy_df.merge(drift_df, on='window')
    profile.to_csv("data/outputs/framing_dynamics_profile.csv", index=False)
    
    print("\n[✔] Done! Results generated in 'data/outputs/framing_dynamics_profile.csv'")

if __name__ == "__main__":
    main()
