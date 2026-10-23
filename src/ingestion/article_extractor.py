"""Extract accessible article text and publication metadata from saved HTML.

This module performs no network requests. It deliberately returns review or failure
statuses when a page does not provide enough evidence for a complete article.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from time import strptime
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from src.ingestion.manifest import url_identity

MIN_CONTENT_WORDS = 80
MIN_SOURCE_WORD_COUNT_RATIO = 0.8
MIN_BODY_CONTENT_OVERLAP = 0.75

_BODY_SELECTORS = {
    "nyt": (
        'section[name="articleBody"]',
        'div[name="articleBody"]',
        '[data-testid="article-body"]',
    ),
    "wapo": (
        'div[data-qa="article-body"].type-text',
        '[data-qa="article-body-content"]',
        "article .article-body",
    ),
    "fox": (".article-content .article-body", "article .article-body"),
    "cbs": (
        "article.content-article section.content__body",
        "article.content-article div.content__body",
        "article .article-body",
    ),
    "bbc": ('article [data-component="text-block"]', "article .story-body__inner"),
}
_OUTLET_DOMAINS = {
    "nyt": {"nytimes.com"},
    "wapo": {"washingtonpost.com", "wapo.st"},
    "fox": {"foxnews.com"},
    "cbs": {"cbsnews.com"},
    "bbc": {"bbc.com", "bbc.co.uk"},
}

_PUBLICATION_META = {
    "article:published_time",
    "datepublished",
    "pubdate",
    "publishdate",
    "publication_date",
    "parsely-pub-date",
    "sailthru.date",
    "dc.date",
    "dcterms.date",
}
_UPDATE_META = {
    "article:modified_time",
    "datemodified",
    "og:updated_time",
    "dcterms.modified",
    "last-modified",
    "lastmod",
    "updated_time",
}
_TITLE_META = {"og:title", "twitter:title", "parsely-title", "title"}
_NON_ARTICLE_ATTR = re.compile(
    r"newsletter|subscription|subscribe|cookie|consent|paywall|softwall|hardwall|"
    r"related|recirc|recommend|promo|caption|footer|byline|author-bio|"
    r"article-meta|share-tools|social-share|image-ct|media-container|"
    r"(?:^|[\s_-])(?:ad|ads|advertisement|advertising|nav|hidden|sr-only)(?:$|[\s_-])|"
    r"(?:^|\s)(?:credit|credits|photo-credit|image-credit)(?:$|\s)",
    re.IGNORECASE,
)
_RESTRICTION_ATTR = re.compile(
    r"(?:^|[\s_-])(?:paywall|softwall|hardwall|paygate|regwall)(?:$|[\s_-])|"
    r"gateway[-_ ]?(?:content|container)|"
    r"subscription[-_ ]?overlay|metered[-_ ]?paywall",
    re.IGNORECASE,
)
_PAYWALL_TEXT = re.compile(
    r"(?:subscribe|sign in|log in|register) to (?:continue|keep) reading|"
    r"(?:reached|used up) your (?:free )?article limit|"
    r"(?:only available|exclusively) (?:to|for) subscribers|"
    r"to read the full article,? (?:subscribe|sign in|register)",
    re.IGNORECASE,
)
_BOILERPLATE_TEXT = re.compile(
    r"^(?:subscribe\b|sign up\b|register\b|sign in\b|log in\b|"
    r"click here\b|tap here\b|read (?:more|next|also)\b|watch (?:more|next)\b|"
    r"related (?:article|story|stories|content)\b|more from\b|newsletter\b|"
    r"advertisement\b|copyright\b|all rights reserved\b|©|"
    r"this material may not be published\b|to leave without signing in\b|"
    r"enjoy unlimited access\b)",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"\b[\w]+(?:[’'-][\w]+)*\b", re.UNICODE)
_MONTH_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\.?\s+\d{1,2},?\s+\d{4}\b",
    re.IGNORECASE,
)
_STRUCTURAL_ATTRIBUTES = {
    "class",
    "id",
    "role",
    "data-qa",
    "data-testid",
    "data-test-id",
    "data-test",
    "data-component",
    "data-module",
    "data-widget",
    "data-block-type",
}
_REPEATED_BLOCK_SELECTORS = {
    ("wapo", 'div[data-qa="article-body"].type-text'),
    ("bbc", 'article [data-component="text-block"]'),
}
_IDENTITY_ATTRIBUTES = ("data-path", "data-url", "data-canonical-url", "itemid")
_TIME_EXCLUDED_ATTR = re.compile(
    r"related|recirc|recommend|promo|caption|newsletter|footer|"
    r"(?:^|[\s_-])(?:ad|ads|advertisement)(?:$|[\s_-])",
    re.IGNORECASE,
)


def _text(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("@value", ""))
    if isinstance(value, list):
        return next((text for item in value if (text := _text(item))), "")
    return (
        re.sub(r"\s+", " ", unescape(str(value))).strip() if value is not None else ""
    )


def _url_key(value: str, base_url: str = "") -> tuple[str, str] | None:
    try:
        parsed = urlsplit(urljoin(base_url, value))
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed.netloc.lower().removeprefix("www."), parsed.path.rstrip("/") or "/"


def _identity(value: str, base_url: str = "") -> tuple[str, str, str] | None:
    if not value:
        return None
    try:
        return url_identity(urljoin(base_url, value))
    except (TypeError, ValueError):
        return None


def _absolute_url(value: object, base_url: str) -> str:
    if isinstance(value, dict):
        value = value.get("@id") or value.get("url")
    value = _text(value)
    if not value:
        return ""
    candidate = urljoin(base_url, value)
    return candidate if _url_key(candidate) else ""


def _canonical_link(soup: BeautifulSoup, url: str) -> str:
    for link in soup.find_all("link"):
        rel = link.get("rel", [])
        if "canonical" in [str(item).lower() for item in rel]:
            candidate = _absolute_url(link.get("href"), url)
            if candidate:
                return candidate
    return ""


def _walk_json(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _article_urls(article: dict, base_url: str) -> list[str]:
    values = [article.get("url"), article.get("@id"), article.get("mainEntityOfPage")]
    return [
        candidate for value in values if (candidate := _absolute_url(value, base_url))
    ]


def _independent_article_url(article: dict, base_url: str) -> str:
    for field in ("url", "mainEntityOfPage", "@id"):
        value = article.get(field)
        if isinstance(value, dict):
            value = value.get("@id") or value.get("url")
        value = _text(value)
        if not value or value.startswith("#"):
            continue
        candidate = _absolute_url(value, base_url)
        if candidate:
            return urldefrag(candidate)[0]
    return ""


def _select_json_article(
    soup: BeautifulSoup, url: str, canonical_url: str
) -> tuple[dict, bool]:
    candidates = []
    page_keys = {_identity(url), _identity(canonical_url)} - {None}
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        for item in _walk_json(payload):
            types = item.get("@type", [])
            types = types if isinstance(types, list) else [types]
            if not any(
                str(kind).rsplit("/", 1)[-1].endswith("Article") for kind in types
            ):
                continue
            article_keys = {_identity(value) for value in _article_urls(item, url)} - {
                None
            }
            matches_page = bool(article_keys & page_keys)
            score = 100 * matches_page + 10 * bool(item.get("articleBody"))
            score += 4 * bool(item.get("headline")) + 2 * bool(
                item.get("datePublished")
            )
            candidates.append((score, matches_page, item))
    if not candidates:
        return {}, False
    candidates.sort(key=lambda item: item[0], reverse=True)
    ambiguous = len(candidates) > 1 and (
        not candidates[0][1] or candidates[0][0] == candidates[1][0]
    )
    return candidates[0][2], ambiguous


def _meta_values(scope: Tag | None, names: set[str]) -> list[str]:
    values = []
    if scope is None:
        return values
    metas = [scope] if scope.name == "meta" else scope.find_all("meta")
    for meta in metas:
        keys = [meta.get("property"), meta.get("name"), meta.get("itemprop")]
        if any(_text(key).lower() in names for key in keys):
            value = _text(meta.get("content"))
            if value:
                values.append(value)
    return values


def _metadata_values(
    soup: BeautifulSoup, primary_root: Tag | None, names: set[str]
) -> list[str]:
    values = _meta_values(soup.head, names)
    if primary_root is None:
        return values
    for meta in primary_root.find_all("meta"):
        excluded = False
        for node in (meta, *meta.parents):
            if not isinstance(node, Tag):
                continue
            if node.name in {
                "aside",
                "nav",
                "footer",
                "figure",
            } or _TIME_EXCLUDED_ATTR.search(_attributes(node)):
                excluded = True
                break
            if node is primary_root:
                break
        if not excluded:
            values.extend(_meta_values(meta, names))
    return values


def _time_values(primary_root: Tag | None) -> tuple[list[str], list[str]]:
    published, updated = [], []
    if primary_root is None:
        return published, updated
    for tag in primary_root.find_all("time"):
        ancestors = []
        for node in (tag, *tag.parents):
            if not isinstance(node, Tag):
                continue
            ancestors.append(node)
            if node is primary_root:
                break
        if any(
            node.name in {"aside", "nav", "footer", "figure"}
            or _TIME_EXCLUDED_ATTR.search(_attributes(node))
            for node in ancestors
        ):
            continue
        explicit_role = _text(tag.get("itemprop")).lower() in {
            "datepublished",
            "datemodified",
        } or tag.has_attr("pubdate")
        header_context = any(
            node.name == "header"
            or re.search(
                r"article-(?:update-)?date|content__header|content__meta|timestamp|publish-date|updated-date",
                _attributes(node),
                re.IGNORECASE,
            )
            for node in ancestors
        )
        if not explicit_role and not header_context:
            continue
        attributes = f"{_attributes(tag)} {_text(tag.get('itemprop'))} {'pubdate' if tag.has_attr('pubdate') else ''}"
        parent_text = (
            tag.parent.get_text(" ", strip=True) if isinstance(tag.parent, Tag) else ""
        )
        parent_attributes = (
            _attributes(tag.parent) if isinstance(tag.parent, Tag) else ""
        )
        context = f"{attributes} {parent_attributes} {tag.get_text(' ', strip=True)} {parent_text[:160]}".lower()
        is_update = bool(re.search(r"modified|updated|update-date|lastmod", context))
        is_publication = bool(
            re.search(
                r"published|datepublished|pubdate|publish-date|article-date", context
            )
        )
        value = _text(
            tag.get("datetime") or tag.get("content") or tag.get_text(" ", strip=True)
        )
        if not value:
            continue
        if is_update and not is_publication:
            updated.append(value)
        elif is_publication and not is_update:
            published.append(value)
    return published, updated


def _calendar_date(value: str) -> str:
    value = re.sub(
        r"^(?:published|updated|modified)(?:\s+on)?\s*:?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )
    if re.match(r"^\d{4}-\d{2}-\d{2}", value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.date().isoformat()
        except ValueError:
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                return ""
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    match = _MONTH_DATE_RE.search(value)
    if match:
        candidate = (
            match.group().replace("Sept", "Sep").replace(".", "").replace(",", "")
        )
        for pattern in ("%B %d %Y", "%b %d %Y"):
            try:
                parsed = strptime(candidate, pattern)
                return date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday).isoformat()
            except ValueError:
                pass
    for pattern in ("%m/%d/%Y", "%Y/%m/%d"):
        try:
            parsed = strptime(value, pattern)
            return date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday).isoformat()
        except ValueError:
            pass
    return ""


def _choose_date(values: list[str], kind: str) -> tuple[str, str, list[str]]:
    values = list(dict.fromkeys(value for value in values if value))
    valid = [(value, _calendar_date(value)) for value in values]
    valid = [(value, calendar_date) for value, calendar_date in valid if calendar_date]
    reasons = []
    if not valid:
        if values:
            reasons.append(f"invalid_{kind}_date")
        elif kind == "publication":
            reasons.append("missing_publication_date")
        return values[0] if values else "", "", reasons
    if len(valid) != len(values):
        reasons.append(f"invalid_{kind}_metadata")
    if len({calendar_date for _, calendar_date in valid}) > 1:
        reasons.append(f"conflicting_{kind}_dates")
    return valid[0][0], valid[0][1], reasons


def _attributes(tag: Tag) -> str:
    parts = []
    for key, value in tag.attrs.items():
        if key not in _STRUCTURAL_ATTRIBUTES:
            continue
        value = (
            " ".join(str(item) for item in value)
            if isinstance(value, list)
            else _text(value)
        )
        parts.append(f"{key} {value}")
    return " ".join(parts)


def _restricted(soup: BeautifulSoup, article: dict) -> bool:
    for item in _walk_json(article):
        accessible = item.get("isAccessibleForFree")
        if accessible is False or _text(accessible).lower() == "false":
            return True
    if any(_RESTRICTION_ATTR.search(_attributes(tag)) for tag in soup.find_all(True)):
        return True
    return bool(_PAYWALL_TEXT.search(soup.get_text(" ", strip=True)))


def _page_problem(soup: BeautifulSoup) -> str:
    heading = " ".join(
        tag.get_text(" ", strip=True) for tag in soup.find_all(["title", "h1"])
    )
    page_text = soup.get_text(" ", strip=True)
    sample = (
        heading if len(_WORD_RE.findall(page_text)) > 200 else f"{heading} {page_text}"
    )
    if re.search(
        r"access denied|verify (?:that )?you are human|enable javascript and cookies|"
        r"unusual traffic|captcha|just a moment",
        sample,
        re.IGNORECASE,
    ):
        return "access_blocked"
    if re.search(
        r"page not found|article (?:is )?no longer available|content is unavailable",
        sample,
        re.IGNORECASE,
    ):
        return "page_unavailable"
    return ""


def _inline_text(tag: Tag) -> str:
    pieces = []
    for node in tag.descendants:
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            pieces.append(str(node))
        elif isinstance(node, Tag) and node.name == "br":
            pieces.append("\n")
    return re.sub(r"\s+", " ", "".join(pieces)).strip()


def _link_only_promo(tag: Tag, text: str) -> bool:
    links = tag.find_all("a")
    if not links:
        return False
    outside = []
    for string in tag.find_all(string=True):
        if not string.find_parent("a"):
            outside.append(str(string))
    if re.search(r"\w", " ".join(outside)):
        return False
    letters = "".join(character for character in text if character.isalpha())
    return bool(_BOILERPLATE_TEXT.search(text)) or (
        bool(letters) and letters.isupper() and len(_WORD_RE.findall(text)) <= 30
    )


def _clean_blocks(container: Tag) -> list[str]:
    fragment = BeautifulSoup(str(container), "html.parser")
    for comment in fragment.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in list(fragment.find_all(True)):
        if tag.parent is None:
            continue
        style = _text(tag.get("style")).lower()
        if (
            tag.name
            in {
                "script",
                "style",
                "noscript",
                "nav",
                "aside",
                "footer",
                "header",
                "form",
                "button",
                "figure",
                "figcaption",
                "iframe",
                "video",
                "audio",
                "picture",
                "svg",
                "canvas",
            }
            or tag.has_attr("hidden")
            or _text(tag.get("aria-hidden")).lower() == "true"
            or "display:none" in style.replace(" ", "")
            or "visibility:hidden" in style.replace(" ", "")
            or _NON_ARTICLE_ATTR.search(_attributes(tag))
        ):
            tag.decompose()
    paragraphs = []
    for block in fragment.find_all(["p", "li", "h2", "h3"]):
        if block.name == "li" and block.find("p"):
            continue
        if block.name == "li" and block.find(["ul", "ol"]):
            block = BeautifulSoup(str(block), "html.parser").find("li")
            for nested in block.find_all(["ul", "ol"]):
                nested.decompose()
        text = _inline_text(block)
        if not text or _BOILERPLATE_TEXT.search(text) or _link_only_promo(block, text):
            continue
        paragraphs.append(text)
    return paragraphs


def _structured_blocks(value: object) -> list[str]:
    if isinstance(value, list):
        return [paragraph for item in value for paragraph in _structured_blocks(item)]
    if isinstance(value, dict):
        value = value.get("@value", "")
    if not isinstance(value, str) or not value.strip():
        return []
    if re.search(r"<\s*[a-z][^>]*>", value, re.IGNORECASE):
        blocks = _clean_blocks(BeautifulSoup(value, "html.parser"))
        return blocks or _clean_blocks(BeautifulSoup(f"<p>{value}</p>", "html.parser"))
    paragraphs = [
        re.sub(r"\s+", " ", unescape(part)).strip()
        for part in re.split(r"\r?\n+", value)
    ]
    return [
        paragraph
        for paragraph in paragraphs
        if paragraph and not _BOILERPLATE_TEXT.search(paragraph)
    ]


def _outlet_key(outlet: str, url: str) -> str:
    try:
        hostname = urlsplit(url).netloc
    except ValueError:
        hostname = ""
    text = f"{outlet} {hostname}".lower()
    for key, aliases in {
        "nyt": ("new york times", "nytimes", " nyt"),
        "wapo": ("washington post", "washingtonpost", "wapo"),
        "fox": ("fox news", "foxnews"),
        "cbs": ("cbs news", "cbsnews"),
        "bbc": ("bbc news", "bbc.com", "bbc.co.uk"),
    }.items():
        if any(alias in text for alias in aliases):
            return key
    return ""


def _matches_outlet_host(url: str, outlet_key: str) -> bool:
    key = _url_key(url)
    if not key:
        return False
    hostname = key[0].split(":", 1)[0]
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in _OUTLET_DOMAINS.get(outlet_key, set())
    )


def _container_identity(container: Tag, url: str) -> tuple[Tag | None, tuple | None]:
    for node in (container, *container.parents):
        if not isinstance(node, Tag) or node.name in {"body", "html", "[document]"}:
            break
        for attribute in _IDENTITY_ATTRIBUTES:
            value = _text(node.get(attribute))
            identity = _identity(value, url)
            if identity:
                return node, identity
    return None, None


def _grouping_root(container: Tag, key: str, selector: str) -> Tag:
    if (key, selector) not in _REPEATED_BLOCK_SELECTORS:
        return container
    for parent in container.parents:
        if not isinstance(parent, Tag) or parent.name in {"body", "html", "[document]"}:
            break
        if parent.name == "article":
            return parent
        if key == "wapo" and _text(parent.get("data-qa")) in {
            "article",
            "article-content",
        }:
            return parent
    return container


def _select_dom_containers(
    soup: BeautifulSoup, outlet: str, url: str, canonical_url: str
) -> tuple[list[Tag], str, list[str], Tag | None]:
    key = _outlet_key(outlet, url)
    page_keys = {_identity(url), _identity(canonical_url)} - {None}
    for selector in _BODY_SELECTORS.get(key, ()):
        containers = soup.select(selector)
        container_ids = {id(container) for container in containers}
        groups = {}
        for container in containers:
            if any(id(parent) in container_ids for parent in container.parents):
                continue
            root = _grouping_root(container, key, selector)
            identity_root, identity = _container_identity(root, url)
            if identity and identity not in page_keys:
                continue
            group = groups.setdefault(
                id(root),
                {
                    "containers": [],
                    "identity_root": identity_root,
                    "matched": identity in page_keys if identity else False,
                },
            )
            group["containers"].append(container)
        candidates = list(groups.values())
        matched = [group for group in candidates if group["matched"]]
        candidates = matched or candidates
        if candidates:
            ambiguous = len(candidates) > 1
            selected = candidates[0]
            reasons = ["ambiguous_article_roots"] if ambiguous else []
            primary_root = (
                selected["identity_root"]
                if selected["matched"] and not ambiguous
                else None
            )
            return (
                selected["containers"],
                f"dom:{key}:{selector}",
                reasons,
                primary_root,
            )
    return [], "none", [], None


def _word_count(value: object) -> int | None:
    match = re.fullmatch(
        r"\s*((?:\d{1,3}(?:,\d{3})+|\d+))(?:\s+words)?\s*",
        str(value),
        re.IGNORECASE,
    )
    if not match:
        return None
    digits = match.group(1).replace(",", "")
    if not digits:
        return None
    count = int(digits)
    return count if count > 0 else None


def _content_overlap(first: list[str], second: list[str]) -> float | None:
    def shingles(paragraphs: list[str]) -> set[tuple[str, ...]]:
        normalized = " ".join(paragraphs).casefold().replace("’", "'")
        words = _WORD_RE.findall(normalized)
        if len(words) < 5:
            return {tuple(words)} if words else set()
        return {tuple(words[index : index + 5]) for index in range(len(words) - 4)}

    first_shingles, second_shingles = shingles(first), shingles(second)
    if not first_shingles or not second_shingles:
        return None
    return len(first_shingles & second_shingles) / min(
        len(first_shingles), len(second_shingles)
    )


def _finish(record: dict, reasons: list[str], fatal: bool = False) -> dict:
    record["content_sha256"] = hashlib.sha256(
        record["content"].encode("utf-8")
    ).hexdigest()
    record["extraction_status"] = (
        "failed" if fatal else "needs_review" if reasons else "success"
    )
    record["extraction_reasons"] = json.dumps(
        list(dict.fromkeys(reasons)), ensure_ascii=False
    )
    return record


def extract_article(html: str, url: str, outlet: str, retrieved_at: str) -> dict:
    """Extract one article without fetching pages or reading restricted body content.

    ``date`` is the calendar date in the chosen publication source, without a UTC
    conversion. ``published_at`` and ``updated_at`` retain the source strings.
    Paragraphs are separated by blank lines and the SHA-256 covers that exact text.
    """
    record = {
        "url": url,
        "canonical_url": url,
        "outlet": outlet,
        "title": "",
        "date": "",
        "published_at": "",
        "updated_at": "",
        "retrieved_at": retrieved_at,
        "content": "",
        "content_sha256": "",
        "extraction_method": "none",
        "extraction_status": "failed",
        "extraction_reasons": "[]",
    }
    if not isinstance(html, str) or not html.strip():
        return _finish(record, ["empty_html"], fatal=True)

    soup = BeautifulSoup(html, "html.parser")
    canonical = _canonical_link(soup, url)
    article, ambiguous = _select_json_article(soup, url, canonical)
    article_url = _independent_article_url(article, url)
    record["canonical_url"] = canonical or article_url or url
    containers, dom_method, dom_reasons, primary_root = _select_dom_containers(
        soup, outlet, url, record["canonical_url"]
    )
    title_values = [
        _text(article.get("headline") or article.get("name"))
    ] + _metadata_values(soup, primary_root, _TITLE_META)
    heading_scope = primary_root
    if heading_scope is None and containers:
        heading_scope = containers[0].find_parent("article") or containers[0]
    heading = heading_scope.find("h1") if heading_scope is not None else None
    title_values.append(_inline_text(heading) if heading else "")
    record["title"] = next((value for value in title_values if value), "")

    time_published, time_updated = _time_values(primary_root)
    pub_values = (
        [_text(article.get("datePublished"))]
        + _metadata_values(soup, primary_root, _PUBLICATION_META)
        + time_published
    )
    update_values = (
        [_text(article.get("dateModified"))]
        + _metadata_values(soup, primary_root, _UPDATE_META)
        + time_updated
    )
    record["published_at"], record["date"], reasons = _choose_date(
        pub_values, "publication"
    )
    record["updated_at"], _, update_reasons = _choose_date(update_values, "update")
    reasons.extend(update_reasons)
    reasons.extend(dom_reasons)
    canonical_evidence = [value for value in (canonical, article_url) if value]
    if not canonical_evidence:
        reasons.append("missing_canonical_identity")
    elif any(_identity(value) != _identity(url) for value in canonical_evidence):
        reasons.append("requested_canonical_mismatch")
    if ambiguous:
        reasons.append("ambiguous_article_metadata")
    if not record["title"]:
        reasons.append("missing_title")
    if not outlet:
        reasons.append("missing_outlet")
    if not retrieved_at:
        reasons.append("missing_retrieved_at")
    if not _url_key(url):
        reasons.append("invalid_url")

    outlet_key = _outlet_key(outlet, "")
    if not outlet_key:
        reasons.append("unsupported_outlet")
    elif not _matches_outlet_host(url, outlet_key):
        return _finish(record, reasons + ["url_outlet_mismatch"], fatal=True)
    elif not _matches_outlet_host(record["canonical_url"], outlet_key):
        return _finish(record, reasons + ["canonical_outlet_mismatch"], fatal=True)

    if _restricted(soup, article):
        return _finish(record, reasons + ["restricted_content"], fatal=True)
    problem = _page_problem(soup)
    if problem:
        return _finish(record, reasons + [problem], fatal=True)

    structured = _structured_blocks(article.get("articleBody"))
    dom = [
        paragraph for container in containers for paragraph in _clean_blocks(container)
    ]
    count_values = [article.get("wordCount")] + _metadata_values(
        soup, primary_root, {"wordcount"}
    )
    count_values = [
        value for value in count_values if value is not None and _text(value)
    ]
    parsed_counts = [_word_count(value) for value in count_values]
    if any(count is None for count in parsed_counts):
        reasons.append("invalid_word_count")
    source_count = next((count for count in parsed_counts if count is not None), None)
    structured_count = len(_WORD_RE.findall(" ".join(structured)))
    dom_count = len(_WORD_RE.findall(" ".join(dom)))
    structured_short = structured_count < MIN_CONTENT_WORDS
    structured_truncated = (
        source_count is not None
        and structured_count < source_count * MIN_SOURCE_WORD_COUNT_RATIO
    )
    length_disagreement = (
        source_count is None
        and structured_count > 0
        and dom_count > 0
        and abs(structured_count - dom_count) >= 40
        and min(structured_count, dom_count) < max(structured_count, dom_count) * 0.75
    )
    overlap = _content_overlap(structured, dom)
    overlap_disagreement = overlap is not None and overlap < MIN_BODY_CONTENT_OVERLAP
    body_disagreement = length_disagreement or overlap_disagreement
    if body_disagreement:
        reasons.append(
            f"body_source_disagreement: json_ld_words={structured_count}, dom_words={dom_count}, normalized_overlap={overlap:.3f}"
        )
    prefer_longer_dom = (
        structured_short or structured_truncated or length_disagreement
    ) and dom_count > structured_count
    if structured and not prefer_longer_dom:
        paragraphs, method = structured, "json_ld:articleBody"
    else:
        paragraphs, method = dom, dom_method
    record["content"] = "\n\n".join(paragraphs)
    record["extraction_method"] = method

    if not paragraphs:
        return _finish(record, reasons + ["article_body_not_found"], fatal=True)
    if re.search(
        r"^article from .+ covering events on .+\. url:",
        record["content"],
        re.IGNORECASE,
    ):
        return _finish(record, reasons + ["placeholder_content"], fatal=True)
    count = len(_WORD_RE.findall(record["content"]))
    if count < MIN_CONTENT_WORDS:
        reasons.append("short_content")
    if method.startswith("dom:nyt:"):
        reasons.append("unverified_nyt_dom_template")
    if source_count is not None and count < source_count * MIN_SOURCE_WORD_COUNT_RATIO:
        reasons.append(
            f"likely_truncated: extracted_words={count}, source_word_count={source_count}"
        )
    return _finish(record, reasons)
