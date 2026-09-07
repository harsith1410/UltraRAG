from rag.core.db import sessionLocal
from rag.core.models_db import Subject, Documents
from rag.core.retrieval import invalidate_bm25_cache
from rag.core.vector_db import returnchroma


def create_subject(name: str):
    db = sessionLocal()
    try:
        instance = Subject(name=name)
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
