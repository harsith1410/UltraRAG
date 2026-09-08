import os
from mistralai.client import Mistral
from dotenv import load_dotenv
import base64

load_dotenv()

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

# figures smaller than this are almost always logos or bullet glyphs
IMAGE_MIN_SIZE = 120
IMAGE_LIMIT = 40


def _encode(file_path):
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _ocr(document, with_images=False):
    client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

    kwargs = {}
    if with_images:
        kwargs = {
            "include_image_base64": True,
            "image_limit": IMAGE_LIMIT,
            "image_min_size": IMAGE_MIN_SIZE,
        }

    return client.ocr.process(
        model="mistral-ocr-latest",
        document=document,
        table_format="markdown",
        **kwargs,
    )


def _join_pages(response):
    return "\n\n---\n\n".join(page.markdown for page in response.pages)


def _strip_data_uri(encoded: str) -> tuple[str, str]:
    """Mistral may return a bare base64 payload or a full data URI."""
    if encoded.startswith("data:"):
        header, _, payload = encoded.partition(",")
        mime = header[5:].split(";")[0] or "image/png"
        return payload, mime
    return encoded, "image/png"


def _collect_images(response) -> list:
    images = []
    for page in response.pages:
        for image in page.images or []:
            if not image.image_base64:
                continue
            payload, mime = _strip_data_uri(image.image_base64)
            ext = os.path.splitext(image.id)[1].lower()
            images.append({
                "id": image.id,
                "page": page.index + 1,
                "base64": payload,
                "mime": MIME_TYPES.get(ext, mime),
            })
    return images


def _page_text(response) -> dict:
    return {page.index + 1: page.markdown for page in response.pages}


def process_file(file_path):
    return _join_pages(_ocr({
        "type": "document_url",
        "document_url": f"data:application/pdf;base64,{_encode(file_path)}",
    }))


def process_file_with_images(file_path):
    """Return (markdown, images, page_text) for a PDF, with embedded figures extracted."""
    response = _ocr({
        "type": "document_url",
        "document_url": f"data:application/pdf;base64,{_encode(file_path)}",
    }, with_images=True)

    return _join_pages(response), _collect_images(response), _page_text(response)


def process_image(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    mime = MIME_TYPES.get(ext, "image/png")
    return _join_pages(_ocr({
        "type": "image_url",
        "image_url": f"data:{mime};base64,{_encode(file_path)}",
    }))


def process_image_with_images(file_path):
    """For a standalone image the file itself is the figure worth describing."""
    ext = os.path.splitext(file_path)[1].lower()
    mime = MIME_TYPES.get(ext, "image/png")
    encoded = _encode(file_path)

    markdown = _join_pages(_ocr({
        "type": "image_url",
        "image_url": f"data:{mime};base64,{encoded}",
    }))

    image = {
        "id": os.path.basename(file_path),
        "page": 1,
        "base64": encoded,
        "mime": mime,
    }

    return markdown, [image], {1: markdown}
