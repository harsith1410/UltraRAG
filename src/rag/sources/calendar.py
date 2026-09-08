"""Google Calendar: list upcoming events and add new ones (deadlines, exams, revision blocks)."""
import logging
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build

from rag.core.google_auth import get_google_creds

CALENDAR_ID = 'primary'
DEFAULT_DAYS = 7
DEFAULT_MAX_RESULTS = 20

_service = None


logger = logging.getLogger(__name__)


def calendar_service():
    global _service
    if _service is None:
        _service = build('calendar', 'v3', credentials=get_google_creds())
    return _service


def _when(endpoint: dict) -> tuple[str, bool]:
    """Calendar returns dateTime for timed events and date for all-day ones."""
    if 'dateTime' in endpoint:
        return endpoint['dateTime'], False
    return endpoint.get('date', ''), True


def list_events(days: int = DEFAULT_DAYS, max_results: int = DEFAULT_MAX_RESULTS) -> list:
    now = datetime.now(timezone.utc)

    response = calendar_service().events().list(
        calendarId=CALENDAR_ID,
        timeMin=now.isoformat(),
        timeMax=(now + timedelta(days=days)).isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy='startTime',
    ).execute()

    events = []
    for event in response.get('items', []):
        start, all_day = _when(event.get('start', {}))
        end, _ = _when(event.get('end', {}))
        events.append({
            "id": event.get('id'),
            "summary": event.get('summary', '(no title)'),
            "start": start,
            "end": end,
            "all_day": all_day,
            "location": event.get('location'),
            "link": event.get('htmlLink'),
        })

    logger.info("calendar events listed | count=%d", len(events))
    return events


def create_event(summary: str, start: str, end: str = None,
                 description: str = None, location: str = None,
                 all_day: bool = False) -> dict:
    """Create an event. `start`/`end` are ISO strings; all-day events use plain dates."""
    if all_day:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date() if end else start_date + timedelta(days=1)
        endpoints = {
            "start": {"date": start_date.isoformat()},
            "end": {"date": end_date.isoformat()},
        }
    else:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end) if end else start_dt + timedelta(hours=1)
        endpoints = {
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }

    body = {"summary": summary, **endpoints}
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    event = calendar_service().events().insert(calendarId=CALENDAR_ID, body=body).execute()
    logger.info("calendar event created | id=%s summary=%s start=%s",
                event.get('id'), summary, start)

    return {
        "id": event.get('id'),
        "summary": event.get('summary'),
        "start": _when(event.get('start', {}))[0],
        "end": _when(event.get('end', {}))[0],
        "link": event.get('htmlLink'),
    }
