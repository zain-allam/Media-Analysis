import argparse
import hashlib
import html
import json
import logging
import os
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

from src.ingestion.manifest import url_identity

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

RAW_REQUIRED_COLUMNS = {
    "url",
    "canonical_url",
    "outlet",
    "title",
    "date",
    "published_at",
    "updated_at",
    "retrieved_at",
    "content",
    "content_sha256",
    "extraction_method",
    "extraction_status",
    "extraction_reasons",
}
PROCESSED_REQUIRED_COLUMNS = RAW_REQUIRED_COLUMNS | {
    "raw_content",
    "raw_content_sha256",
    "cleaned_content_sha256",
    "window",
}

_PLACEHOLDERS = {
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "not available",
    "unavailable",
    "placeholder",
    "placeholder content",
    "[placeholder]",
    "untitled",
    "untitled article",
    "no title",
    "title unavailable",
    "no content",
    "no content available",
    "content unavailable",
    "article unavailable",
    "failed to extract",
    "extraction failed",
    "access denied",
    "forbidden",
    "not found",
    "error",
}


def load_config(config_path: str = "config.yaml") -> dict:
    """Load the project configuration file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")
    with open(config_path, "r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def clean_text(text: str) -> str:
    """Normalize text for NLP while retaining paragraph and inline word boundaries.

    Lowercasing and URL removal are retained for compatibility. Horizontal whitespace
    is normalized within each line; line breaks remain, with at most one blank line
    between paragraphs. This function does not attempt to repair already-merged words.
    """
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</(?:p|div|section|article|h[1-6])\s*>", "\n\n", text, flags=re.IGNORECASE
    )
    text = html.unescape(re.sub(r"</?[A-Za-z][^>]*>", "", text))
    text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.IGNORECASE)
    text = "\n".join(
        re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n")
    )
    return re.sub(r"\n{3,}", "\n\n", text).strip().lower()


def _timestamp(value):
    if value is None or isinstance(value, (int, float, bool)):
        return None
    if isinstance(value, str) and value.strip().lower() in {
        "",
        "nan",
        "nat",
        "none",
        "now",
        "today",
    }:
        return None
    try:
        parsed = pd.Timestamp(value)
        return None if pd.isna(parsed) else parsed
    except (TypeError, ValueError, OverflowError):
        return None


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _calendar_date(value):
    parsed = _timestamp(value)
    # Take the calendar date before any UTC conversion: 23:00-07:00 remains that day.
    return parsed.date() if parsed is not None else None


def _window_bounds(time_windows: dict) -> dict:
    if not isinstance(time_windows, dict) or not time_windows:
        raise ValueError("Configuration must define at least one time window.")
    bounds = {}
    for window_id, info in time_windows.items():
        try:
            start = _calendar_date(info["start_date"])
            end = _calendar_date(info["end_date"])
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"Time window {window_id!r} must define start_date and end_date."
            ) from exc
        if start is None or end is None or start > end:
            raise ValueError(f"Time window {window_id!r} has invalid date bounds.")
        bounds[window_id] = (start, end)
    return bounds


def assign_time_window(date_str: str, time_windows: dict) -> str:
    """Map a publication calendar date to a configured window, including its last day.

    Timestamp offsets are preserved when choosing the calendar day. Missing and invalid
    dates return the historical sentinel strings; invalid window configuration raises
    ValueError instead of silently assigning an arbitrary window.
    """
    if _is_blank(date_str):
        return "UNMAPPED"
    publication_date = _calendar_date(date_str)
    if publication_date is None:
        return "INVALID_DATE"
    for window_id, (start, end) in _window_bounds(time_windows).items():
        if start <= publication_date <= end:
            return window_id
    return "OUT_OF_BOUNDS"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _has_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_placeholder(value) -> bool:
    if not _has_text(value):
        return True
    normalized = " ".join(value.lower().split()).strip(" .:;\t\n")
    if normalized in _PLACEHOLDERS:
        return True
    if re.fullmatch(
        r"article from .+ covering events on \d{4}-\d{2}-\d{2}\.\s*url:\s*https?://\S+",
        normalized,
    ):
        return True
    return bool(
        re.fullmatch(
            r"this live coverage has ended\.?\s*for the latest updates,?\s*please go here\.?",
            normalized,
        )
    )


def _canonical_identity(value):
    if not _has_text(value):
        return None
    try:
        return url_identity(value.strip())
    except ValueError:
        return None


def _extraction_reason_list(value):
    def reject_constant(constant):
        raise ValueError(constant)

    try:
        if isinstance(value, str):
            parsed = json.loads(value, parse_constant=reject_constant)
        else:
            parsed = value
        if not isinstance(parsed, list) or not all(
            isinstance(reason, str) for reason in parsed
        ):
            return None
        return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _row_admission_reasons(
    row: dict, time_windows: dict, content_column: str = "content"
) -> list:
    reasons = []
    status = row.get("extraction_status")
    if status != "success":
        reasons.append(f"extraction_status is {status!r}; only 'success' is admitted")
    for field in ("url", "canonical_url"):
        if _canonical_identity(row.get(field)) is None:
            reasons.append(f"{field} is missing or invalid")
    for field in ("outlet", "extraction_method"):
        if not _has_text(row.get(field)):
            reasons.append(f"{field} is empty")
    if _is_placeholder(row.get("title")):
        reasons.append("title is empty or a placeholder")
    content = row.get(content_column)
    if _is_placeholder(content):
        reasons.append(f"{content_column} is empty or a placeholder")
    if _has_text(content):
        expected_hash = row.get("content_sha256")
        if not _has_text(expected_hash) or expected_hash.strip().lower() != _sha256(
            content
        ):
            reasons.append("content_sha256 does not match raw content")
    publication_date = _calendar_date(row.get("date"))
    published_at = _timestamp(row.get("published_at"))
    if publication_date is None:
        reasons.append("date is not a valid publication date")
    if published_at is None:
        reasons.append("published_at is not a valid timestamp")
    elif publication_date is not None and publication_date != published_at.date():
        reasons.append("date does not match the source calendar date in published_at")
    if _timestamp(row.get("retrieved_at")) is None:
        reasons.append("retrieved_at is not a valid timestamp")
    updated_at = row.get("updated_at")
    if not _is_blank(updated_at) and _timestamp(updated_at) is None:
        reasons.append("updated_at is not a valid timestamp")
    extraction_reasons = _extraction_reason_list(row.get("extraction_reasons"))
    if extraction_reasons is None:
        reasons.append("extraction_reasons must be a JSON list of strings")
    elif status == "success" and extraction_reasons:
        reasons.append("success extraction_status requires empty extraction_reasons")
    if publication_date is not None:
        window = assign_time_window(publication_date, time_windows)
        if window not in time_windows:
            reasons.append("publication date is outside configured time windows")
    return reasons


def _schema_error(df: pd.DataFrame, required: set, label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        legacy = (
            " Legacy data without extraction status is not admitted."
            if "extraction_status" in missing
            else ""
        )
        raise ValueError(
            f"{label} dataset is missing required provenance columns: {', '.join(missing)}."
            f"{legacy} Please re-extract articles with the current extractor and run preprocessing."
        )


def validate_processed_dataset(df: pd.DataFrame, time_windows: dict) -> None:
    """Raise ValueError when processed data is unsafe to admit to analysis.

    Legacy processed CSVs intentionally fail because they cannot prove extraction status
    or content provenance. Every row must retain valid raw metadata and hashes, contain
    the current cleaned representation, and have the correct unique URL and time window.
    """
    _schema_error(df, PROCESSED_REQUIRED_COLUMNS, "Processed")
    _window_bounds(time_windows)
    if df.empty:
        raise ValueError(
            "Processed dataset contains zero rows; re-extract and preprocess valid articles before analysis."
        )
    identities = [_canonical_identity(value) for value in df["canonical_url"]]
    duplicate_identities = {
        identity
        for identity, count in Counter(identities).items()
        if identity is not None and count > 1
    }
    failures = []
    for row_number, (_, series) in enumerate(df.iterrows(), 1):
        row = series.to_dict()
        reasons = _row_admission_reasons(row, time_windows, "raw_content")
        raw_content = row.get("raw_content")
        cleaned_content = row.get("content")
        if _has_text(raw_content):
            raw_hash = row.get("raw_content_sha256")
            if not _has_text(raw_hash) or raw_hash.strip().lower() != _sha256(
                raw_content
            ):
                reasons.append("raw_content_sha256 does not match raw_content")
            if cleaned_content != clean_text(raw_content):
                reasons.append("content does not match the cleaned raw_content")
        if _is_placeholder(cleaned_content):
            reasons.append("cleaned content is empty or a placeholder")
        if _has_text(cleaned_content):
            cleaned_hash = row.get("cleaned_content_sha256")
            if not _has_text(cleaned_hash) or cleaned_hash.strip().lower() != _sha256(
                cleaned_content
            ):
                reasons.append("cleaned_content_sha256 does not match content")
        if row.get("window") != assign_time_window(row.get("date"), time_windows):
            reasons.append("window does not match the publication calendar date")
        if identities[row_number - 1] in duplicate_identities:
            reasons.append("duplicate canonical_url")
        if reasons:
            failures.append(
                f"row {row_number} ({row.get('url', '')}): {'; '.join(reasons)}"
            )
    if failures:
        preview = " | ".join(failures[:5])
        raise ValueError(
            f"Processed dataset has {len(failures)} invalid row(s): {preview}"
        )


def _write_exclusions(exclusions: list, exclusions_path) -> None:
    if exclusions_path is None:
        return
    Path(exclusions_path).parent.mkdir(parents=True, exist_ok=True)
    rows = [entry for _, entry in sorted(exclusions, key=lambda item: item[0])]
    pd.DataFrame(rows, columns=["url", "canonical_url", "reason"]).to_csv(
        exclusions_path, index=False
    )


def process_raw_dataset(
    raw_path: str = "data/raw/articles.csv",
    output_path: str = "data/processed/articles_cleaned.csv",
    config_path: str = "config.yaml",
    exclusions_path: str | None = None,
) -> pd.DataFrame:
    """Validate, clean, and save extractor output; optionally save excluded rows' reasons.

    Missing provenance columns (including legacy data without extraction_status) raise
    ValueError and require re-extraction. Invalid rows are excluded, and every otherwise
    valid row in a duplicate canonical URL group is excluded. Zero valid rows raise before
    the processed output is written; the optional exclusions CSV is still produced.
    """
    config = load_config(config_path)
    time_windows = config["time_windows"]
    _window_bounds(time_windows)
    logger.info("Loading raw dataset from '%s'...", raw_path)
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"Raw data file missing at '{raw_path}'.")
    if str(raw_path).endswith(".json"):
        df = pd.read_json(raw_path, convert_dates=False)
    else:
        df = pd.read_csv(raw_path, dtype=object, keep_default_na=False)
    _schema_error(df, RAW_REQUIRED_COLUMNS, "Raw")

    candidates = []
    exclusions = []
    for row_number, (_, series) in enumerate(df.iterrows(), 1):
        row = series.to_dict()
        reasons = _row_admission_reasons(row, time_windows)
        raw_content = row.get("content")
        cleaned_content = clean_text(raw_content)
        if _is_placeholder(cleaned_content):
            reasons.append("cleaned content is empty or a placeholder")
        if reasons:
            exclusions.append(
                (
                    row_number,
                    {
                        "url": row.get("url", ""),
                        "canonical_url": row.get("canonical_url", ""),
                        "reason": "; ".join(reasons),
                    },
                )
            )
            continue
        row["raw_content"] = raw_content
        row["raw_content_sha256"] = _sha256(raw_content)
        row["content"] = cleaned_content
        row["cleaned_content_sha256"] = _sha256(cleaned_content)
        row["date"] = _calendar_date(row["date"]).isoformat()
        row["window"] = assign_time_window(row["date"], time_windows)
        if not isinstance(row["extraction_reasons"], str):
            row["extraction_reasons"] = json.dumps(
                row["extraction_reasons"], ensure_ascii=False
            )
        candidates.append((row_number, row))

    counts = Counter(_canonical_identity(row["canonical_url"]) for _, row in candidates)
    accepted = []
    for row_number, row in candidates:
        if counts[_canonical_identity(row["canonical_url"])] > 1:
            exclusions.append(
                (
                    row_number,
                    {
                        "url": row["url"],
                        "canonical_url": row["canonical_url"],
                        "reason": "duplicate canonical_url",
                    },
                )
            )
        else:
            accepted.append(row)
    _write_exclusions(exclusions, exclusions_path)
    if not accepted:
        raise ValueError(
            f"No valid articles remain after preprocessing ({len(exclusions)} excluded). "
            "Review extraction status and exclusion reasons, then re-extract valid articles."
        )

    processed = pd.DataFrame(accepted)
    validate_processed_dataset(processed, time_windows)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(output_path, index=False)
    logger.info(
        "Processing complete: %d accepted, %d excluded; saved to '%s'.",
        len(processed),
        len(exclusions),
        output_path,
    )
    return processed


def main() -> None:
    """Run preprocessing from the command line and save exclusions by default."""
    parser = argparse.ArgumentParser(
        description="Validate and preprocess extracted articles."
    )
    parser.add_argument(
        "--input", "--raw-path", dest="raw_path", default="data/raw/articles.csv"
    )
    parser.add_argument(
        "--output",
        "--output-path",
        dest="output_path",
        default="data/processed/articles_cleaned.csv",
    )
    parser.add_argument(
        "--config", "--config-path", dest="config_path", default="config.yaml"
    )
    parser.add_argument(
        "--exclusions",
        "--exclusions-path",
        dest="exclusions_path",
        default="data/processed/articles_excluded.csv",
        help="CSV destination for excluded URLs and their reasons.",
    )
    process_raw_dataset(**vars(parser.parse_args()))


if __name__ == "__main__":
    main()
