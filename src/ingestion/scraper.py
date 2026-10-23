from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from src.ingestion.article_extractor import extract_article
from src.ingestion.manifest import OUTLET_HOSTS, url_identity

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Media-Analysis/1.0 (+https://github.com/zain-allam/Media-Analysis)"
}


def _redirect_matches_outlet(url: str, outlet: str) -> bool:
    domains = {host.removeprefix("www.") for host in OUTLET_HOSTS.get(outlet, set())}
    if outlet == "BBC News":
        domains = {"bbc.com", "bbc.co.uk"}
    hostname = urlsplit(url).hostname or ""
    return any(
        hostname == domain or hostname.endswith(f".{domain}") for domain in domains
    )


def scrape_article(url: str, outlet: str, timeout: float = 10) -> dict:
    """Fetch public HTML and return the same status-bearing record as the browser path."""
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        retrieved_at = datetime.now(timezone.utc).isoformat()
        result = extract_article(response.text, url, outlet, retrieved_at)
        result["final_url"] = response.url
        if not _redirect_matches_outlet(response.url, outlet):
            reasons = json.loads(result["extraction_reasons"])
            reasons.append("unexpected_redirect_host")
            result["extraction_reasons"] = json.dumps(reasons)
            result["extraction_status"] = "failed"
            result["content"] = ""
            result["content_sha256"] = hashlib.sha256(b"").hexdigest()
        elif url_identity(response.url) != url_identity(url):
            reasons = json.loads(result["extraction_reasons"])
            reasons.append("redirected_article_identity")
            result["extraction_reasons"] = json.dumps(reasons)
            if result["extraction_status"] != "failed":
                result["extraction_status"] = "needs_review"
        return result
    except requests.RequestException as error:
        logger.error("Error fetching article at %s: %s", url, error)
        result = extract_article("", url, outlet, retrieved_at)
        reasons = json.loads(result["extraction_reasons"])
        reasons.append(f"fetch_error:{type(error).__name__}")
        result["extraction_reasons"] = json.dumps(reasons)
        result["extraction_status"] = "failed"
        result["final_url"] = ""
        return result


def scrape_bbc_article(url: str) -> dict | None:
    """Compatibility wrapper returning only accepted BBC article extractions."""
    result = scrape_article(url, "BBC News")
    if result["extraction_status"] != "success":
        logger.warning(
            "BBC article needs review: %s (%s)", url, result["extraction_reasons"]
        )
        return None
    result["headline"] = result["title"]
    return result
