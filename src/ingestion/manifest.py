"""Parse the article URL list without inventing article metadata or content."""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

OUTLET_HOSTS = {
    "New York Times": {"nytimes.com", "www.nytimes.com"},
    "Washington Post": {"washingtonpost.com", "www.washingtonpost.com"},
    "Fox News": {"foxnews.com", "www.foxnews.com"},
    "CBS News": {"cbsnews.com", "www.cbsnews.com"},
}
OUTLET_LABELS = {**{name: name for name in OUTLET_HOSTS}, "FOX News": "Fox News"}
MANIFEST_FIELDS = ["url", "outlet", "selection_group", "manifest_line"]
TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    """Remove fragments and known tracking parameters, retaining functional queries."""
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid article URL: {url!r}")
    if parsed.username or parsed.password:
        raise ValueError("Article URLs must not contain credentials")
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            urlencode(query),
            "",
        )
    )


def url_identity(url: str) -> tuple[str, str, str]:
    """Return a stable article identity across common URL spelling differences."""
    parsed = urlsplit(normalize_url(url))
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80
    if port is not None and port != default_port:
        hostname = f"{hostname}:{port}"
    path = parsed.path.rstrip("/") or "/"
    if hostname == "cbsnews.com" and path.startswith("/amp/"):
        path = path.removeprefix("/amp")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return hostname, path, query


def parse_manifest(txt_path: str | Path) -> list[dict[str, str | int]]:
    """Read outlet headings, selection groups, and URLs from the source list."""
    records: list[dict[str, str | int]] = []
    seen: set[tuple[str, str, str]] = set()
    outlet: str | None = None
    selection_group = ""

    with Path(txt_path).open(encoding="utf-8-sig") as source:
        for line_number, raw_line in enumerate(source, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if line in OUTLET_LABELS:
                outlet = OUTLET_LABELS[line]
                selection_group = ""
                continue
            if not line.lower().startswith(("http://", "https://")):
                selection_group = line
                continue
            if outlet is None:
                raise ValueError(
                    f"Line {line_number}: URL appears before an outlet heading"
                )

            url = normalize_url(line)
            hostname = urlsplit(url).hostname
            if hostname not in OUTLET_HOSTS[outlet]:
                raise ValueError(
                    f"Line {line_number}: {hostname!r} does not match outlet {outlet!r}"
                )
            identity = url_identity(url)
            if identity in seen:
                raise ValueError(f"Line {line_number}: duplicate article URL {url}")
            seen.add(identity)
            records.append(
                {
                    "url": url,
                    "outlet": outlet,
                    "selection_group": selection_group,
                    "manifest_line": line_number,
                }
            )

    if not records:
        raise ValueError(f"No article URLs found in {txt_path}")
    return records


def write_manifest(
    records: list[dict[str, str | int]], output_path: str | Path
) -> None:
    """Atomically save a URL manifest, refusing to replace an article dataset."""
    destination = Path(output_path)
    if destination.exists():
        with destination.open(newline="", encoding="utf-8-sig") as existing:
            fields = next(csv.reader(existing), [])
        if "content" in fields:
            raise ValueError(
                f"Refusing to replace article content with a URL manifest: {destination}"
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", newline="", encoding="utf-8", dir=destination.parent, delete=False
        ) as handle:
            temporary_path = handle.name
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerows(records)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
