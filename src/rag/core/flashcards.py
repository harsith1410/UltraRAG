import json
import logging

import groq
from dotenv import load_dotenv

from rag.core.chat import get_full_content, get_subject_name_for_docs, resolve_filenames

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = "openai/gpt-oss-120b"
CONTENT_CHAR_LIMIT = 60000


def build_flashcards_prompt(content: str, count: int) -> str:
    template = """
    You are an expert Study Assistant that writes spaced-repetition flashcards.

    ### INSTRUCTIONS ###
    1. Read the ### CONTENT ### and produce up to {count} flashcards covering its most important ideas.
    2. One fact per card. Keep the front a single clear question, the back a short self-contained answer.
    3. Prefer questions that test understanding (why/how, definitions, distinctions, formulas) over trivia.
    4. Do not write cards that need the source in front of you to make sense ("what does the diagram show?").
    5. Plain text only in both fields. No markdown, no numbering, no "Q:" or "A:" prefixes.

    ### OUTPUT FORMAT ###
    Respond with JSON only, matching this shape exactly:
    {{"cards": [{{"front": "question", "back": "answer"}}]}}

    ### CONTENT ###
    {content}
    """

    return template.format(content=content, count=count)


def parse_cards(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    data = json.loads(text)
    cards = data.get("cards", []) if isinstance(data, dict) else data

    cleaned = []
    for card in cards:
        front = str(card.get("front", "")).strip()
        back = str(card.get("back", "")).strip()
        if front and back:
            cleaned.append({"front": front, "back": back})
    return cleaned


def generate_flashcards(doc_ids: list, count: int = 25) -> dict:
    logger.info("flashcards requested | doc_ids=%s count=%d", doc_ids, count)
    doc_names = resolve_filenames(doc_ids)
    content = get_full_content(doc_names)
    if not content.strip():
        logger.warning("flashcards aborted, no content | docs=%s", doc_names)
        return {"cards": [], "subject": "unknown", "deck": "unknown"}

    content = content[:CONTENT_CHAR_LIMIT]
    subject_name = get_subject_name_for_docs(doc_ids)
    prompt = build_flashcards_prompt(content, count)

    client = groq.Groq()
    res = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL,
        response_format={"type": "json_object"},
    )

    cards = parse_cards(res.choices[0].message.content)
    logger.info("flashcards generated | subject=%s cards=%d from %d document(s)",
                subject_name, len(cards), len(doc_names))

    return {
        "cards": cards,
        "subject": subject_name,
        "deck": f"RAG::{subject_name.upper()}",
    }


def cards_to_tsv(cards: list, tags: list = None) -> str:
    """Tab-separated export for manual Anki import when AnkiConnect is unavailable."""
    tag_str = " ".join(tags or [])
    lines = []
    for card in cards:
        front = card["front"].replace("\t", " ").replace("\n", " ")
        back = card["back"].replace("\t", " ").replace("\n", " ")
        lines.append(f"{front}\t{back}\t{tag_str}")
    return "\n".join(lines)
