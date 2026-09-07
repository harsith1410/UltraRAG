import os

from rag.core.db import sessionLocal
from rag.core.google_auth import get_google_creds
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload

from rag.core.ingest import ingest
from rag.core.models_db import Documents

creds = get_google_creds()
drive_service = build('drive', 'v3', credentials=creds)

def list_drive_files(folder_id = "1A2PRgrWoCZ5q7JjEkuGqkSnIlciDLlwL", subject_id = 1):
    FOLDER_ID = folder_id
    db = sessionLocal()

    results = drive_service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name, modifiedTime)"
    ).execute()

    files = results.get('files', [])
    filtered_files = []

    for file in files:
        res = db.query(Documents).filter(Documents.gdrive_id == file.get('id'), Documents.subject_id == subject_id).first()
        if res is not None:
            continue
        else:
            filtered_files.append(file)

    db.close()

    return filtered_files

def download_drive_file(file):
    request = drive_service.files().get_media(fileId=file['id'])
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    buffer.seek(0)
    os.makedirs('./data', exist_ok=True)
    file_loc = os.path.join('./data', f"{file['id']}_{file['name']}")
    with open(file_loc, 'wb') as f:
        f.write(buffer.read())

    return file_loc

def sync_drive_folder(folder_id, subject_id):
    files = list_drive_files(folder_id, subject_id)
    results = []
    for file in files:
        file_loc = download_drive_file(file)
        success, chunk_count = ingest(file_loc, subject_id, gdrive_id=file['id'])
        results.append({"name": file['name'], "success": success, "chunks": chunk_count})
    return results

