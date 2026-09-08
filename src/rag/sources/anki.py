import httpx

ANKI_CONNECT_URL = "http://127.0.0.1:8765"
ANKI_CONNECT_VERSION = 6
DEFAULT_MODEL = "Basic"


class AnkiConnectError(Exception):
    pass


def invoke(action: str, **params):
    payload = {"action": action, "version": ANKI_CONNECT_VERSION, "params": params}
    try:
        response = httpx.post(ANKI_CONNECT_URL, json=payload, timeout=15.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise AnkiConnectError(
            "Could not reach AnkiConnect at "
            f"{ANKI_CONNECT_URL}. Is Anki running with the AnkiConnect add-on installed? ({e})"
        )

    body = response.json()
    if body.get("error") is not None:
        raise AnkiConnectError(body["error"])
    return body.get("result")


def is_available() -> bool:
    try:
        invoke("version")
        return True
    except AnkiConnectError:
        return False


def list_decks() -> list:
    return invoke("deckNames")


def ensure_deck(deck_name: str):
    if deck_name not in list_decks():
        invoke("createDeck", deck=deck_name)


def _to_note(card: dict, deck_name: str, tags: list) -> dict:
    return {
        "deckName": deck_name,
        "modelName": DEFAULT_MODEL,
        "fields": {"Front": card["front"], "Back": card["back"]},
        "tags": tags + card.get("tags", []),
        "options": {"allowDuplicate": False, "duplicateScope": "deck"},
    }


def add_cards(cards: list, deck_name: str, tags: list = None) -> dict:
    """Push cards to Anki. Returns counts of added vs skipped (duplicates)."""
    if not cards:
        return {"added": 0, "skipped": 0, "deck": deck_name}

    tags = tags or []
    ensure_deck(deck_name)

    notes = [_to_note(card, deck_name, tags) for card in cards]
    note_ids = invoke("addNotes", notes=notes)

    added = sum(1 for nid in note_ids if nid is not None)
    return {
        "added": added,
        "skipped": len(note_ids) - added,
        "deck": deck_name,
    }
