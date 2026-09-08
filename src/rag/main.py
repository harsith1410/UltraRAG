import json
import os.path
from typing import List

from fastapi import FastAPI, status, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag.core.chat import run_chat, generate_notes
from rag.core.db import Base, engine
from rag.core.dedupe import NearDuplicate
from rag.core.flashcards import cards_to_tsv, generate_flashcards
from rag.core.ingest import ingest
from rag.core.models_db import Subject
from rag.core.subjects import create_subject, listSubject, deleteSubject, getDocuments
from rag.core.vision import IMAGE_DIR
from rag.core.vector_db import returnchroma
from rag.sources.anki import AnkiConnectError, add_cards, is_available, list_decks
from rag.sources.calendar import create_event, list_events
from rag.sources.converters import SUPPORTED_EXTENSIONS, UnsupportedFormat
from rag.sources.drive import sync_drive_folder
from rag.sources.web import UrlFetchError, save_url_as_markdown

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

class ChatRequest(BaseModel):
    message: str
    model: str = "..."

class NotesRequest(BaseModel):
    doc_ids: List[int]

class UrlRequest(BaseModel):
    url: str
    subject_id: int
    force: bool = False

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

@app.post('/subject/{name}', status_code=status.HTTP_200_OK)
def add_subject(name: str):
    op = create_subject(name.upper())
    if op is None:
        raise HTTPException(status_code=409, detail="A subject with that name already exists")
    return {"SubjectId": op.id}

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

@app.post('/upload', status_code=status.HTTP_200_OK)
async def ingest_file(file: UploadFile=File(), subject_id: int = Form(), force: bool = Form(False)):
    os.makedirs('./data', exist_ok=True)
    file_loc = os.path.join('./data',file.filename)
    with open(file_loc,'wb') as f:
        content = await file.read()
        f.write(content)

    try:
        success, chunk_count, figure_count = ingest(file_loc, subject_id, force=force)
    except UnsupportedFormat as e:
        raise HTTPException(status_code=415, detail=str(e))
    except NearDuplicate as e:
        raise near_duplicate_error(e)

    if success:
        return {"filename": file.filename, "chunks": chunk_count, "figures": figure_count}
    else:
        raise HTTPException(status_code=409, detail="Document already ingested")

@app.get('/formats', status_code=status.HTTP_200_OK)
def supported_formats():
    return {"extensions": SUPPORTED_EXTENSIONS}


@app.post('/ingest/url', status_code=status.HTTP_200_OK)
def ingest_url(body: UrlRequest):
    try:
        file_loc = save_url_as_markdown(body.url)
    except UrlFetchError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        success, chunk_count, figure_count = ingest(file_loc, body.subject_id, force=body.force)
    except NearDuplicate as e:
        raise near_duplicate_error(e)

    if success:
        return {"filename": os.path.basename(file_loc), "chunks": chunk_count, "figures": figure_count}
    raise HTTPException(status_code=409, detail="This page has already been ingested")


@app.get('/images/{file_hash}/{name}')
def get_figure(file_hash: str, name: str):
    # both segments come from stored metadata, but never trust them as a path
    if not file_hash.isalnum() or os.path.basename(name) != name:
        raise HTTPException(status_code=400, detail="Invalid image reference")

    path = os.path.join(IMAGE_DIR, file_hash, name)
    if not os.path.isfile(path):
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
    folder_id = folder_map.get(subject_id)
    if folder_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"No Drive folder mapped for subject {subject_id}. Add it to folder_map in main.py.",
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
