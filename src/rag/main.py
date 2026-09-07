import json
import os.path
from typing import List

from fastapi import FastAPI, status, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag.core.chat import run_chat, generate_notes
from rag.core.db import Base, engine
from rag.core.ingest import ingest
from rag.core.models_db import Subject
from rag.core.subjects import create_subject, listSubject, deleteSubject, getDocuments
from rag.core.vector_db import returnchroma
from rag.sources.drive import sync_drive_folder

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

folder_map = {1:"1Saf3tlmFOCBQSbc2UXKli9SnJ-xgwAkU"}
@app.get('/')
def main():
    return {"Health": "Good"}

@app.post('/subject/{name}', status_code=status.HTTP_200_OK)
def add_subject(name: str):
    op = create_subject(name.upper())
    if op:
        return {"SubjectId": op.id}

@app.get('/subject/', status_code=status.HTTP_200_OK)
def list_subject():
    op = listSubject()
    if op:
        return {"Subjects": op}

@app.get('/subject/{id}/documents', status_code=status.HTTP_200_OK)
def get_documents(id: int):
    op = getDocuments(id)
    if op:
        return {"Documents": op}

@app.delete('/subject/{id}', status_code=status.HTTP_200_OK)
def delete_subject(id: int):
    op = deleteSubject(id)
    if op is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return {"Subject": op}

@app.post('/upload', status_code=status.HTTP_200_OK)
async def ingest_file(file: UploadFile=File(), subject_id: int = Form()):
    os.makedirs('./data', exist_ok=True)
    file_loc = os.path.join('./data',file.filename)
    with open(file_loc,'wb') as f:
        content = await file.read()
        f.write(content)

    success, chunk_count = ingest(file_loc, subject_id)
    if success:
        return {"filename": file.filename, "chunks": chunk_count}
    else:
        raise HTTPException(status_code=409, detail="Document already ingested")

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
                yield f"data: {payload}\n\n"
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


@app.post('/drive/sync/{name}')
def drive_sync(subject_id: int):
    results = sync_drive_folder(folder_map.get(subject_id), subject_id)
    return {"synced": results}