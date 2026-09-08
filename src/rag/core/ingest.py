import logging
import os
import time
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter

from rag.core.db import sessionLocal
from rag.core.dedupe import NearDuplicate, find_near_duplicate
from rag.core.hashing import get_file_hash
from rag.core.models_db import Documents
from rag.core.retrieval import invalidate_bm25_cache
from rag.core.vision import describe_images, is_enabled as vision_enabled
from rag.sources.converters import to_markdown_and_images
from rag.core.vector_db import returnchroma


logger = logging.getLogger(__name__)

BATCH_SIZE = 10

def add_chunks_in_batches(vectorstore, chunks):
    total = len(chunks)
    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        vectorstore.add_documents(batch)


def ingest(filepath: str, subject_id: int, gdrive_id: str = None, force: bool = False):
    started = time.perf_counter()
    file_hash = get_file_hash(filepath)
    logger.info("ingest start | file=%s subject=%s hash=%s gdrive=%s force=%s",
                os.path.basename(filepath), subject_id, file_hash[:8], gdrive_id, force)
    db = sessionLocal()
    try:
        existing = db.query(Documents).filter(
            Documents.file_hash == file_hash,
            Documents.subject_id == subject_id,
            Documents.gdrive_id == gdrive_id
        ).first()
        if existing:
            logger.info("ingest skipped, already present | file=%s subject=%s",
                        os.path.basename(filepath), subject_id)
            return False, None, 0

        source = os.path.basename(filepath)
        markdown, images, page_text = to_markdown_and_images(filepath)
        logger.info("converted to markdown | file=%s chars=%d images=%d",
                    source, len(markdown), len(images))

        header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "Header 1"), ("##", "Header 2")])
        header_splits = header_splitter.split_text(markdown)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=300)
        chunks = text_splitter.split_documents(header_splits)

        for chunk in chunks:
            chunk.metadata["subject_id"] = subject_id
            chunk.metadata["source"] = source
            chunk.metadata["file_hash"] = file_hash

        before_filter = len(chunks)
        chunks = [c for c in chunks if len(c.page_content.strip()) >= 30]
        logger.info("split into chunks | file=%s chunks=%d dropped_short=%d",
                    source, len(chunks), before_filter - len(chunks))

        if not force:
            duplicate = find_near_duplicate(chunks, subject_id)
            if duplicate is not None:
                logger.warning("near-duplicate detected | file=%s similar_to=%s",
                               source, duplicate.source)
                raise duplicate

        figures = []
        if vision_enabled() and images:
            figures = describe_images(images, source, file_hash, page_text)
            for figure in figures:
                figure.metadata["subject_id"] = subject_id

        vectorstore = returnchroma()
        add_chunks_in_batches(vectorstore, chunks + figures)
        logger.info("indexed to chroma | file=%s added=%d collection_total=%d",
                    source, len(chunks) + len(figures), vectorstore._collection.count())

        doc_record = Documents(subject_id=subject_id, filename=source, file_hash=file_hash, gdrive_id=gdrive_id)
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)

        invalidate_bm25_cache(subject_id)

        logger.info("ingest done | file=%s subject=%s chunks=%d figures=%d doc_id=%s in %.1fs",
                    source, subject_id, len(chunks), len(figures), doc_record.id,
                    time.perf_counter() - started)
        return True, len(chunks), len(figures)
    except NearDuplicate:
        # expected control flow, already logged as a warning above
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("ingest failed, rolled back | file=%s subject=%s",
                         os.path.basename(filepath), subject_id)
        raise
    finally:
        db.close()