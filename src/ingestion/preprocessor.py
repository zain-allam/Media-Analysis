import os
import re
import yaml
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def load_config(config_path: str = "../../config.yaml") -> dict:
    """Loads project configuration file."""
    # Resolve relative path if executed from root or src/ingestion
    if not os.path.exists(config_path):
        config_path = "config.yaml"
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")
        
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def clean_text(text: str) -> str:
    """Cleans and standardizes raw article content for NLP processing."""
    if not isinstance(text, str):
        return ""
    
    text = text.lower()
    text = re.sub(r'https?://\S+|www\.\S+', '', text)  # Remove links
    text = re.sub(r'<.*?>', '', text)                  # Remove HTML tags
    text = re.sub(r'\s+', ' ', text).strip()            # Normalize space
    
    return text


def assign_time_window(date_str: str, time_windows: dict) -> str:
    """Maps article publication dates to defined temporal windows (W1 - W5)."""
    if pd.isna(date_str) or not date_str:
        return "UNMAPPED"
        
    try:
        pub_date = pd.to_datetime(date_str, utc=True).tz_localize(None)
    except Exception:
        return "INVALID_DATE"

    for w_id, w_info in time_windows.items():
        start = pd.to_datetime(w_info["start_date"])
        end = pd.to_datetime(w_info["end_date"])
        if start <= pub_date <= end:
            return w_id
            
    return "OUT_OF_BOUNDS"


def process_raw_dataset(
    raw_path: str = "data/raw/articles.csv",
    output_path: str = "data/processed/articles_cleaned.csv",
    config_path: str = "config.yaml"
) -> pd.DataFrame:
    """Main function to clean raw CSV/JSON data and save processed corpus."""
    config = load_config(config_path)
    time_windows = config["time_windows"]
    
    logging.info(f"Loading raw dataset from '{raw_path}'...")
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"Raw data file missing at '{raw_path}'.")
        
    df = pd.read_json(raw_path) if raw_path.endswith(".json") else pd.read_csv(raw_path)
    
    required_cols = {'date', 'content', 'outlet'}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Input dataset is missing required columns: {missing}")
        
    logging.info("Cleaning text content...")
    df['content'] = df['content'].apply(clean_text)
    
    logging.info("Assigning temporal windows (W1 - W5)...")
    df['window'] = df['date'].apply(lambda d: assign_time_window(d, time_windows))
    
    valid_mask = df['window'].isin(time_windows.keys()) & (df['content'].str.len() > 50)
    filtered_df = df[valid_mask].copy()
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    filtered_df.to_csv(output_path, index=False)
    logging.info(f"[✔] Processing complete -> Saved to '{output_path}'")
    
    return filtered_df


if __name__ == "__main__":
    process_raw_dataset()
