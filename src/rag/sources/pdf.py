import os
from mistralai.client import Mistral
from dotenv import load_dotenv
import base64

load_dotenv()

def process_file(file_path):
    client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{encoded}",
        },
        table_format="markdown",
    )

    pages_md = [page.markdown for page in response.pages]

    return "\n\n---\n\n".join(pages_md)