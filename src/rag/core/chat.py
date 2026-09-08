from datetime import datetime
from typing import AsyncGenerator
import groq
from dotenv import load_dotenv

from rag.core.retrieval import hybrid_search
from rag.core.subjects import getDocuments
from rag.core.vector_db import returnchroma
from rag.core.db import sessionLocal
from rag.core.models_db import Documents, Subject

load_dotenv()

def build_prompt(query: str, docs: list, history: list) -> tuple[str, dict]:

    context_texts = []
    sources = []
    figures = []

    for doc in docs:
        source = doc.metadata.get('source', 'unknown')
        if source not in sources:
            sources.append(source)

        if doc.metadata.get('kind') == 'image':
            figures.append({
                "source": source,
                "page": doc.metadata.get('page'),
                "url": f"/images/{doc.metadata.get('file_hash')}/{doc.metadata.get('image_id')}",
            })

        context_texts.append(f"[Source: {source}]\n{doc.page_content}")

    context_str = "\n\n---\n\n".join(context_texts)

    if isinstance(history, list):
        history_str = "\n".join([str(h) for h in history])
    else:
        history_str = str(history)

    template = """
            ### INSTRUCTION ###
            You are a helpful Academic Assistant. 
            1. Answer the question using the CONTEXT and HISTORY provided. 
            2. If the context is irrelevant or contains nonsense, use your general knowledge and the conversation history to answer.
            3. Be direct. Do NOT explain your thought process or mention if you are using context or the internet.

            ### CONTEXT ###
            {context}

            ### HISTORY ###
            {history}

            ### USER QUERY ###
            {query}
    """

    prompt = template.format(context=context_str, history=history_str, query=query)

    return prompt, {"sources": sources, "figures": figures}

async def stream_completion(prompt: str, model: str) -> AsyncGenerator[str, None]:
    client = groq.AsyncGroq()
    stream = await client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], stream=True)
    async for chunk in stream:
        content = chunk.choices[0].delta.content
        if content is not None:
            yield content

async def run_chat(message: str, subject_id: int, model: str) -> AsyncGenerator[tuple[str, ...], None]:
    docs = hybrid_search(message, subject_id)
    prompt, citations = build_prompt(message,docs,history=[])
    async for token in stream_completion(prompt, model):
        yield ("token",token)
    yield ("citations", citations)

def resolve_filenames(doc_ids: list) -> list:
    db = sessionLocal()
    try:
        docs = db.query(Documents).filter(Documents.id.in_(doc_ids)).all()
        return [d.filename for d in docs]
    finally:
        db.close()

def get_subject_name_for_docs(doc_ids: list) -> str:
    db = sessionLocal()
    try:
        doc = db.query(Documents).filter(Documents.id.in_(doc_ids)).first()
        if doc is None:
            return "unknown"
        subject = db.query(Subject).filter(Subject.id == doc.subject_id).first()
        return subject.name if subject else "unknown"
    finally:
        db.close()

def getSelectedDocs(doc_names: list) -> list:
    vs = returnchroma()
    content = []
    for name in doc_names:
        res = vs.get(where={"source": name})
        content.append(res)
    return content

def get_full_content(doc_names: list) -> str:
    results = getSelectedDocs(doc_names)
    all_text = []
    for res in results:
        all_text.extend(res['documents'])
    return "\n\n".join(all_text)

def build_notes_prompt(content: str) -> str:
    template = """
    You are an expert Study Assistant and Notes Bot. Your objective is to synthesize the provided context into comprehensive, highly readable notes using strict Markdown formatting.

    ### INSTRUCTIONS ###
    1. **Primary Source:** Base your notes primarily on the information provided in the ### CONTENT ### section.
    2. **Knowledge Expansion:** You may seamlessly integrate your own internal knowledge to elaborate on complex topics, define jargon, or provide helpful analogies that make the retrieved content easier to understand.
    3. **Structure & Scaffolding:** Organize the information logically. Use bullet points for itemized lists, bold text for key terminology, and blockquotes (>) for crucial definitions or rules.
    4. **Output Format:** Strictly follow the structural skeleton provided below.

    ### OUTPUT SKELETON ###
    **[Insert Catchy Title for the Notes]**

    **Overview**
    [1-2 sentences summarizing the core theme of the text]

    **Key Concepts**
    * **[Concept 1]:** [Brief definition or explanation based on context + your knowledge]
    * **[Concept 2]:** [Brief definition or explanation]

    **Detailed Breakdown**
    * [Use nested bullet points to break down the mechanics, history, or deeper details of the text]
      * [Sub-point elaborating on the detail]
      * [Sub-point providing an example]

    **Summary Takeaways**
    * [Bullet 1]
    * [Bullet 2]

    ### CONTENT ###
    {content}
    """

    prompt = template.format(content=content)

    return prompt

def generate_notes(doc_ids: list) -> str:
    doc_names = resolve_filenames(doc_ids)
    content = get_full_content(doc_names)
    prompt = build_notes_prompt(content)
    subject_name = get_subject_name_for_docs(doc_ids)

    client = groq.Groq()
    res = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-120b"
    )

    notes_body = res.choices[0].message.content

    frontmatter = f"""---
tags: [{subject_name.lower()}]
created: {datetime.now().isoformat()}
---

"""
    return frontmatter + notes_body