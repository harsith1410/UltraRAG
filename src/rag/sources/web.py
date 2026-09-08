"""URL -> markdown, so a web page can go through the same splitter pipeline as a file."""
import os
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify

MAX_BYTES = 5 * 1024 * 1024
STRIP_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript", "form", "iframe"]
MAIN_SELECTORS = ["main", "article", "[role=main]", "#content", ".content", "#main"]


class UrlFetchError(Exception):
    pass


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:80] or "page"


def fetch_url(url: str) -> tuple[str, str]:
    """Fetch a page and return (markdown, title)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlFetchError(f"Only http(s) URLs are supported, got '{parsed.scheme or 'no scheme'}'")

    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True,
                             headers={"User-Agent": "rag-ingest/0.1"})
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise UrlFetchError(f"Could not fetch {url}: {e}")

    content_type = response.headers.get("content-type", "")
    body = response.content[:MAX_BYTES]

    if "text/html" not in content_type:
        # plain text, markdown, or anything else textual: take it as-is
        return body.decode(response.encoding or "utf-8", errors="replace"), parsed.netloc

    soup = BeautifulSoup(body, "lxml")
    for tag in soup(STRIP_TAGS):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else parsed.netloc

    root = None
    for selector in MAIN_SELECTORS:
        root = soup.select_one(selector)
        if root is not None:
            break
    if root is None:
        root = soup.body or soup

    markdown = markdownify(str(root), heading_style="ATX", strip=["a", "img"])
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

    return markdown, title


def save_url_as_markdown(url: str) -> str:
    """Fetch a URL and write it to ./data as markdown, returning the local path."""
    markdown, title = fetch_url(url)
    if not markdown.strip():
        raise UrlFetchError(f"No readable text found at {url}")

    os.makedirs('./data', exist_ok=True)
    file_loc = os.path.join('./data', f"{_slugify(title)}.md")
    with open(file_loc, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n\nSource: {url}\n\n{markdown}")

    return file_loc
