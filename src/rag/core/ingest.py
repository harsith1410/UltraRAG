import os
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter

from rag.core.db import sessionLocal
from rag.core.hashing import get_file_hash
from rag.core.models_db import Documents
from rag.sources.pdf import process_file
from rag.core.vector_db import returnchroma


BATCH_SIZE = 10

def add_chunks_in_batches(vectorstore, chunks):
    total = len(chunks)
    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        vectorstore.add_documents(batch)


def ingest(filepath: str, subject_id: int, gdrive_id: str = None):
    file_hash = get_file_hash(filepath)
    db = sessionLocal()
    try:
        existing = db.query(Documents).filter(
            Documents.file_hash == file_hash,
            Documents.subject_id == subject_id,
            Documents.gdrive_id == gdrive_id
        ).first()
        if existing:
            return False, None

        markdown = process_file(filepath)

        header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "Header 1"), ("##", "Header 2")])
        header_splits = header_splitter.split_text(markdown)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=300)
        chunks = text_splitter.split_documents(header_splits)

        for chunk in chunks:
            chunk.metadata["subject_id"] = subject_id
            chunk.metadata["source"] = os.path.basename(filepath)
            chunk.metadata["file_hash"] = file_hash

        chunks = [c for c in chunks if len(c.page_content.strip()) >= 30]

        vectorstore = returnchroma()
        add_chunks_in_batches(vectorstore, chunks)
        print("count right after add:", vectorstore._collection.count())

        doc_record = Documents(subject_id=subject_id, filename=os.path.basename(filepath), file_hash=file_hash, gdrive_id=gdrive_id)
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)

        return True, len(chunks)
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()