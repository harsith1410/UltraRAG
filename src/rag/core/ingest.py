import os
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter

from rag.core.db import sessionLocal
from rag.core.dedupe import find_near_duplicate
from rag.core.hashing import get_file_hash
from rag.core.models_db import Documents
from rag.core.retrieval import invalidate_bm25_cache
from rag.core.vision import describe_images, is_enabled as vision_enabled
from rag.sources.converters import to_markdown_and_images
from rag.core.vector_db import returnchroma


BATCH_SIZE = 10

def add_chunks_in_batches(vectorstore, chunks):
    total = len(chunks)
    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        vectorstore.add_documents(batch)


def ingest(filepath: str, subject_id: int, gdrive_id: str = None, force: bool = False):
    file_hash = get_file_hash(filepath)
    db = sessionLocal()
    try:
        existing = db.query(Documents).filter(
            Documents.file_hash == file_hash,
            Documents.subject_id == subject_id,
            Documents.gdrive_id == gdrive_id
        ).first()
        if existing:
            return False, None, 0

        source = os.path.basename(filepath)
        markdown, images, page_text = to_markdown_and_images(filepath)

        header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "Header 1"), ("##", "Header 2")])
        header_splits = header_splitter.split_text(markdown)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=300)
        chunks = text_splitter.split_documents(header_splits)

        for chunk in chunks:
            chunk.metadata["subject_id"] = subject_id
            chunk.metadata["source"] = source
            chunk.metadata["file_hash"] = file_hash

        chunks = [c for c in chunks if len(c.page_content.strip()) >= 30]

        if not force:
            duplicate = find_near_duplicate(chunks, subject_id)
            if duplicate is not None:
                raise duplicate

        figures = []
        if vision_enabled() and images:
            figures = describe_images(images, source, file_hash, page_text)
            for figure in figures:
                figure.metadata["subject_id"] = subject_id

        vectorstore = returnchroma()
        add_chunks_in_batches(vectorstore, chunks + figures)
        print("count right after add:", vectorstore._collection.count())

        doc_record = Documents(subject_id=subject_id, filename=source, file_hash=file_hash, gdrive_id=gdrive_id)
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)

        invalidate_bm25_cache(subject_id)

        return True, len(chunks), len(figures)
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()