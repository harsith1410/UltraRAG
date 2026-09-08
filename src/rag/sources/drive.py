import logging
import os

from rag.core.db import sessionLocal
from rag.core.google_auth import get_google_creds
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload

from rag.core.dedupe import NearDuplicate
from rag.core.ingest import ingest
from rag.core.models_db import Documents
from rag.sources.converters import UnsupportedFormat

logger = logging.getLogger(__name__)

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

    logger.info("drive listing | folder=%s found=%d new=%d subject=%s",
                FOLDER_ID, len(files), len(filtered_files), subject_id)
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
    payload = buffer.read()
    with open(file_loc, 'wb') as f:
        f.write(payload)

    logger.info("drive download | name=%s id=%s bytes=%d", file['name'], file['id'], len(payload))
    return file_loc

def sync_drive_folder(folder_id, subject_id):
    logger.info("drive sync start | folder=%s subject=%s", folder_id, subject_id)
    files = list_drive_files(folder_id, subject_id)
    results = []
    for file in files:
        file_loc = download_drive_file(file)
        try:
            success, chunk_count, figure_count = ingest(file_loc, subject_id, gdrive_id=file['id'])
        except (NearDuplicate, UnsupportedFormat) as e:
            # one bad or duplicate file shouldn't abort the whole sync
            logger.warning("drive file skipped | name=%s reason=%s", file['name'], e)
            results.append({"name": file['name'], "success": False, "chunks": None, "skipped": str(e)})
            continue
        results.append({
            "name": file['name'],
            "success": success,
            "chunks": chunk_count,
            "figures": figure_count,
        })

    ingested = sum(1 for r in results if r.get("success"))
    logger.info("drive sync done | folder=%s subject=%s ingested=%d skipped=%d",
                folder_id, subject_id, ingested, len(results) - ingested)
    return results

