import chromadb
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

client = chromadb.HttpClient(host='localhost', port=8000)
embedding = OllamaEmbeddings(model="nomic-embed-text")

def returnchroma():
    chroma = Chroma(client=client, embedding_function=embedding, collection_name="docs")
    return chroma