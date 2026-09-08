"""Vision pass over extracted diagrams, so figures become searchable text."""
import base64
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from langchain_core.documents import Document

load_dotenv()

logger = logging.getLogger(__name__)

VISION_MODEL = os.getenv("VISION_MODEL", "gemini-flash-latest")
MAX_IMAGES_PER_DOC = int(os.getenv("MAX_IMAGES_PER_DOC", "20"))
MAX_WORKERS = 4
MIN_DESCRIPTION_LEN = 40
SKIP_TOKEN = "SKIP"

IMAGE_DIR = os.path.join('.', 'data', 'images')

PROMPT = """You are indexing figures from academic course material so they can be found by search.

Describe this figure as text. Follow these rules:
1. Start with one sentence naming what the figure is (flowchart, circuit, graph, anatomical diagram, table, screenshot, ...) and what it depicts.
2. Transcribe every label, axis name, unit, legend entry and annotated value you can read.
3. Describe the structure: what connects to what, the order of steps, the trend of a curve.
4. State only what is visible. Do not speculate about material that isn't shown.
5. No markdown headings and no preamble — plain prose and short lines only.

If the image carries no study value (a logo, a decorative border, a page header, a blank or unreadable scan), reply with exactly: {skip}

Surrounding page text, for context only:
{context}
"""


def is_enabled() -> bool:
    return os.getenv("ENABLE_IMAGE_EXTRACTION", "1") not in ("0", "false", "False")


def _client():
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=VISION_MODEL,
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0,
    )


def describe_image(client, image: dict, context: str = "") -> str | None:
    """Return a searchable description, or None if the figure is skippable or the call fails."""
    from langchain_core.messages import HumanMessage

    prompt = PROMPT.format(skip=SKIP_TOKEN, context=context[:1500] or "(none)")
    message = HumanMessage(content=[
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": f"data:{image['mime']};base64,{image['base64']}"},
    ])

    try:
        text = client.invoke([message]).content
    except Exception as e:
        logger.warning("vision call failed | image=%s: %s", image["id"], e)
        return None

    if isinstance(text, list):
        text = " ".join(part.get("text", "") for part in text if isinstance(part, dict))

    text = (text or "").strip()
    if text.startswith(SKIP_TOKEN) or len(text) < MIN_DESCRIPTION_LEN:
        logger.debug("figure skipped as low value | image=%s", image["id"])
        return None
    logger.debug("figure described | image=%s chars=%d", image["id"], len(text))
    return text


def save_image(image: dict, file_hash: str) -> str:
    """Persist the figure next to the corpus so the UI can display it later."""
    folder = os.path.join(IMAGE_DIR, file_hash)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, image['id'])
    with open(path, 'wb') as f:
        f.write(base64.b64decode(image['base64']))
    return path


def describe_images(images: list, source: str, file_hash: str,
                    page_text: dict = None) -> list:
    """Turn extracted figures into Documents ready for the vector store."""
    if not images or not is_enabled():
        return []

    page_text = page_text or {}
    total = len(images)
    images = images[:MAX_IMAGES_PER_DOC]
    if total > len(images):
        logger.warning("figure cap hit | source=%s extracted=%d describing=%d (MAX_IMAGES_PER_DOC)",
                       source, total, len(images))
    logger.info("vision pass start | source=%s figures=%d model=%s", source, len(images), VISION_MODEL)
    client = _client()

    def work(image):
        description = describe_image(client, image, page_text.get(image['page'], ""))
        if description is None:
            return None

        try:
            path = save_image(image, file_hash)
        except Exception as e:
            logger.warning("could not save figure | image=%s: %s", image["id"], e)
            path = ""

        return Document(
            page_content=f"[Figure on page {image['page']} of {source}]\n{description}",
            metadata={
                "source": source,
                "file_hash": file_hash,
                "kind": "image",
                "page": image['page'],
                "image_id": image['id'],
                "image_path": path,
            },
        )

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(work, images))

    kept = [doc for doc in results if doc is not None]
    logger.info("vision pass done | source=%s kept=%d skipped=%d",
                source, len(kept), len(results) - len(kept))
    return kept
