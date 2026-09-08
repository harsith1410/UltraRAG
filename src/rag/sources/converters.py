"""Dispatch any supported source file to markdown for the splitter pipeline."""
import os

from rag.sources.docx_pptx import docx_to_markdown, pptx_to_markdown
from rag.sources.pdf import (
    process_file,
    process_file_with_images,
    process_image,
    process_image_with_images,
)


class UnsupportedFormat(Exception):
    pass


def _read_text(file_path: str) -> str:
    with open(file_path, encoding='utf-8', errors='replace') as f:
        return f.read()


CONVERTERS = {
    '.pdf': process_file,
    '.docx': docx_to_markdown,
    '.pptx': pptx_to_markdown,
    '.md': _read_text,
    '.markdown': _read_text,
    '.txt': _read_text,
    '.png': process_image,
    '.jpg': process_image,
    '.jpeg': process_image,
    '.webp': process_image,
}

# formats we can also pull embedded figures out of
IMAGE_CONVERTERS = {
    '.pdf': process_file_with_images,
    '.png': process_image_with_images,
    '.jpg': process_image_with_images,
    '.jpeg': process_image_with_images,
    '.webp': process_image_with_images,
}

SUPPORTED_EXTENSIONS = sorted(CONVERTERS)


def _extension(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in CONVERTERS:
        raise UnsupportedFormat(
            f"'{ext or file_path}' is not a supported format. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    return ext


def to_markdown(file_path: str) -> str:
    return CONVERTERS[_extension(file_path)](file_path)


def to_markdown_and_images(file_path: str) -> tuple[str, list, dict]:
    """Return (markdown, images, page_text). Formats without figures yield empty extras."""
    ext = _extension(file_path)
    converter = IMAGE_CONVERTERS.get(ext)
    if converter is None:
        return CONVERTERS[ext](file_path), [], {}
    return converter(file_path)
