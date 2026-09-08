import os
import shutil

from rag.core.db import sessionLocal
from rag.core.models_db import Subject, Documents
from rag.core.retrieval import invalidate_bm25_cache
from rag.core.vector_db import returnchroma
from rag.core.vision import IMAGE_DIR


def create_subject(name: str, gdrive_folder_id: str = None):
    db = sessionLocal()
    try:
        instance = Subject(name=name, gdrive_folder_id=gdrive_folder_id or None)
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()

def listSubject():
    db = sessionLocal()
    try:
        subjects = db.query(Subject).all()
        return subjects
    except Exception:
        return None
    finally:
        db.close()

def deleteSubject(id: int):
    db = sessionLocal()
    try:
        subject = db.query(Subject).filter(Subject.id == id).first()
        if subject is None:
            return None

        vs = returnchroma()
        vs._collection.delete(where={"subject_id": id})

        db.query(Documents).filter(Documents.subject_id == id).delete()
        db.delete(subject)
        db.commit()
        invalidate_bm25_cache(id)
        return subject
    except Exception as e:
        db.rollback()
        print(f"delete failed: {e}")
        return None
    finally:
        db.close()

def getDocuments(id: int):
    db = sessionLocal()
    try:
        documents = db.query(Documents).filter(Documents.subject_id==id).all()
        if len(documents)==0:
            return []
        else:
            db.close()
            return documents
    except Exception as e:
        print(f"Document Fetch failed: {e}")


def get_subject(id: int):
    db = sessionLocal()
    try:
        return db.query(Subject).filter(Subject.id == id).first()
    finally:
        db.close()


def delete_documents(doc_ids: list):
    """Delete specific documents: their Chroma chunks, figures on disk, and DB rows."""
    if not doc_ids:
        return {"deleted": 0, "filenames": []}

    db = sessionLocal()
    try:
        docs = db.query(Documents).filter(Documents.id.in_(doc_ids)).all()
        if not docs:
            return {"deleted": 0, "filenames": []}

        vs = returnchroma()
        for doc in docs:
            # scope to the subject too: the same file can be ingested under several
            # subjects, and those copies must survive
            vs._collection.delete(where={"$and": [
                {"subject_id": doc.subject_id},
                {"file_hash": doc.file_hash},
            ]})

        filenames = [doc.filename for doc in docs]
        subject_ids = {doc.subject_id for doc in docs}
        hashes = {doc.file_hash for doc in docs}

        db.query(Documents).filter(
            Documents.id.in_([doc.id for doc in docs])
        ).delete(synchronize_session=False)
        db.commit()

        # only drop a figure folder once no surviving row points at that hash
        for file_hash in hashes:
            if db.query(Documents).filter(Documents.file_hash == file_hash).first() is None:
                shutil.rmtree(os.path.join(IMAGE_DIR, file_hash), ignore_errors=True)

        for subject_id in subject_ids:
            invalidate_bm25_cache(subject_id)

        return {"deleted": len(docs), "filenames": filenames}
    except Exception as e:
        db.rollback()
        print(f"document delete failed: {e}")
        return None
    finally:
        db.close()
