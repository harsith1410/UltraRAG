import json
import logging
import os.path
import time
import uuid
from typing import List

from fastapi import FastAPI, Request, status, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag.core.chat import run_chat, generate_notes
from rag.core.db import Base, engine, ensure_schema
from rag.core.logging_config import setup_logging
from rag.core.dedupe import NearDuplicate
from rag.core.flashcards import cards_to_tsv, generate_flashcards
from rag.core.ingest import ingest
from rag.core.models_db import Subject
from rag.core.subjects import (
    create_subject,
    listSubject,
    deleteSubject,
    getDocuments,
    get_subject,
    delete_documents,
)
from rag.core.vision import IMAGE_DIR
from rag.core.vector_db import returnchroma
from rag.sources.anki import AnkiConnectError, add_cards, is_available, list_decks
from rag.sources.calendar import create_event, list_events
from rag.sources.converters import SUPPORTED_EXTENSIONS, UnsupportedFormat
from rag.sources.drive import sync_drive_folder

setup_logging()
logger = logging.getLogger("rag.api")

app = FastAPI()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """One line in, one line out, for every endpoint call."""
    request_id = uuid.uuid4().hex[:8]
    client = request.client.host if request.client else "-"
    logger.info("--> %s %s %s | client=%s", request_id, request.method, request.url.path, client)

    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - started) * 1000
        logger.exception("<-- %s %s %s | UNHANDLED after %.0fms",
                         request_id, request.method, request.url.path, elapsed)
        raise

    elapsed = (time.perf_counter() - started) * 1000
    level = logging.WARNING if response.status_code >= 400 else logging.INFO
    logger.log(level, "<-- %s %s %s | %s in %.0fms",
               request_id, request.method, request.url.path, response.status_code, elapsed)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
ensure_schema()
logger.info("database schema ready")

class ChatRequest(BaseModel):
    message: str
    model: str = "..."

class NotesRequest(BaseModel):
    doc_ids: List[int]

class SubjectRequest(BaseModel):
    name: str
    gdrive_folder_id: str | None = None

class DeleteDocumentsRequest(BaseModel):
    doc_ids: List[int]

class EventRequest(BaseModel):
    summary: str
    start: str
    end: str | None = None
    description: str | None = None
    location: str | None = None
    all_day: bool = False

class FlashcardsRequest(BaseModel):
    doc_ids: List[int]
    count: int = 25

class Flashcard(BaseModel):
    front: str
    back: str

class PushFlashcardsRequest(BaseModel):
    cards: List[Flashcard]
    deck: str
    tags: List[str] = []

folder_map = {1:"1Saf3tlmFOCBQSbc2UXKli9SnJ-xgwAkU"}

def near_duplicate_error(e: NearDuplicate) -> HTTPException:
    return HTTPException(status_code=409, detail={
        "reason": "near_duplicate",
        "message": str(e),
        "similar_to": e.source,
        "similarity": round(e.similarity, 3),
        "matched": e.matched,
        "sampled": e.sampled,
    })


@app.get('/')
def main():
    return {"Health": "Good"}

@app.post('/subject', status_code=status.HTTP_200_OK)
def add_subject(body: SubjectRequest):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Subject name cannot be empty")

    folder_id = (body.gdrive_folder_id or "").strip() or None
    op = create_subject(name.upper(), folder_id)
    if op is None:
        raise HTTPException(status_code=409, detail="A subject with that name already exists")
    return {"SubjectId": op.id, "name": op.name, "gdrive_folder_id": op.gdrive_folder_id}

@app.get('/subject/', status_code=status.HTTP_200_OK)
def list_subject():
    op = listSubject()
    return {"Subjects": op or []}

@app.get('/subject/{id}/documents', status_code=status.HTTP_200_OK)
def get_documents(id: int):
    op = getDocuments(id)
    return {"Documents": op or []}

@app.delete('/subject/{id}', status_code=status.HTTP_200_OK)
def delete_subject(id: int):
    op = deleteSubject(id)
    if op is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return {"Subject": op}

@app.delete('/documents', status_code=status.HTTP_200_OK)
def remove_documents(body: DeleteDocumentsRequest):
    op = delete_documents(body.doc_ids)
    if op is None:
        raise HTTPException(status_code=500, detail="Could not delete those documents")
    if op["deleted"] == 0:
        raise HTTPException(status_code=404, detail="No matching documents found")
    return op


@app.post('/upload', status_code=status.HTTP_200_OK)
async def ingest_file(file: UploadFile=File(), subject_id: int = Form(), force: bool = Form(False)):
    os.makedirs('./data', exist_ok=True)
    file_loc = os.path.join('./data',file.filename)
    with open(file_loc,'wb') as f:
        content = await file.read()
        f.write(content)
    logger.info("upload received | file=%s bytes=%d subject=%s force=%s",
                file.filename, len(content), subject_id, force)

    try:
        success, chunk_count, figure_count = ingest(file_loc, subject_id, force=force)
    except UnsupportedFormat as e:
        logger.warning("upload rejected | file=%s reason=%s", file.filename, e)
        raise HTTPException(status_code=415, detail=str(e))
    except NearDuplicate as e:
        logger.warning("upload blocked as near-duplicate | file=%s similar_to=%s", file.filename, e.source)
        raise near_duplicate_error(e)

    if success:
        return {"filename": file.filename, "chunks": chunk_count, "figures": figure_count}
    else:
        logger.info("upload skipped, already ingested | file=%s subject=%s", file.filename, subject_id)
        raise HTTPException(status_code=409, detail="Document already ingested")

@app.get('/formats', status_code=status.HTTP_200_OK)
def supported_formats():
    return {"extensions": SUPPORTED_EXTENSIONS}


@app.get('/images/{file_hash}/{name}')
def get_figure(file_hash: str, name: str):
    # both segments come from stored metadata, but never trust them as a path
    if not file_hash.isalnum() or os.path.basename(name) != name:
        raise HTTPException(status_code=400, detail="Invalid image reference")

    path = os.path.join(IMAGE_DIR, file_hash, name)
    if not os.path.isfile(path):
        logger.warning("figure not on disk | %s/%s", file_hash, name)
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(path)


@app.get("/debug/chroma-status")
def chroma_status():
    vs = returnchroma()
    return {
        "collection_name": vs._collection.name,
        "count": vs._collection.count(),
    }

@app.post('/chat/{subject_id}', status_code=status.HTTP_200_OK)
async def chat(subject_id: int, body: ChatRequest):

    logger.info("chat | subject=%s model=%s chars=%d", subject_id, body.model, len(body.message))

    async def event_generator():
        async for kind, payload in run_chat(
            message=body.message,
            subject_id=subject_id,
            model=body.model
        ):
            if kind == "token":
                yield f"data: {json.dumps(payload)}\n\n"
            elif kind == "citations":
                yield f"event: citations\n"
                yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.post('/notes/generate')
def notes(body: NotesRequest):
    result = generate_notes(body.doc_ids)
    return {"notes": result}


@app.post('/drive/sync/{subject_id}')
def drive_sync(subject_id: int):
    subject = get_subject(subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")

    # legacy fallback for subjects created before folder ids were stored on the row
    folder_id = subject.gdrive_folder_id or folder_map.get(subject_id)
    if not folder_id:
        raise HTTPException(
            status_code=400,
            detail=f"No Drive folder set for '{subject.name}'. Add one when creating the subject.",
        )
    results = sync_drive_folder(folder_id, subject_id)
    return {"synced": results}


@app.get('/anki/status')
def anki_status():
    if not is_available():
        return {"available": False, "decks": []}
    return {"available": True, "decks": list_decks()}


@app.post('/flashcards/generate')
def flashcards_generate(body: FlashcardsRequest):
    result = generate_flashcards(body.doc_ids, body.count)
    if not result["cards"]:
        raise HTTPException(status_code=422, detail="No flashcards could be generated from these documents")
    return result


@app.post('/flashcards/push')
def flashcards_push(body: PushFlashcardsRequest):
    cards = [card.model_dump() for card in body.cards]
    try:
        return add_cards(cards, body.deck, body.tags)
    except AnkiConnectError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post('/flashcards/export')
def flashcards_export(body: PushFlashcardsRequest):
    cards = [card.model_dump() for card in body.cards]
    return {"tsv": cards_to_tsv(cards, body.tags)}


@app.get('/calendar/events', status_code=status.HTTP_200_OK)
def calendar_events(days: int = 7, max_results: int = 20):
    try:
        return {"events": list_events(days=days, max_results=max_results)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Calendar lookup failed: {e}")


@app.post('/calendar/events', status_code=status.HTTP_201_CREATED)
def calendar_create(body: EventRequest):
    try:
        return {"event": create_event(
            summary=body.summary,
            start=body.start,
            end=body.end,
            description=body.description,
            location=body.location,
            all_day=body.all_day,
        )}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not create event: {e}")
