import json
import logging
import uuid
import io

import azure.functions as func

from shared import blob_client, search_client, openai_client, cosmos_client

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful assistant that answers questions based solely on the provided context.
If the answer is not found in the context, say "I don't have enough information to answer that."
Always cite the source document(s) you used."""


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"status": "ok"}),
        mimetype="application/json",
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Ingest a document
# ---------------------------------------------------------------------------

@app.route(route="ingest", methods=["POST"])
def ingest(req: func.HttpRequest) -> func.HttpResponse:
    file = req.files.get("file")
    if not file:
        return func.HttpResponse(
            json.dumps({"error": "No file provided. Send a multipart/form-data request with field 'file'."}),
            mimetype="application/json",
            status_code=400,
        )

    doc_id = str(uuid.uuid4())
    file_name = file.filename or f"{doc_id}.bin"
    raw_bytes = file.read()

    # 1. Store raw document in Blob Storage
    blob_client.upload_document(file_name, raw_bytes)

    # 2. Extract text
    text = _extract_text(file_name, raw_bytes)

    # 3. Chunk the text
    chunks = _chunk_text(text)

    # 4. Ensure search index exists
    search_client.ensure_index()

    # 5. Embed + index each chunk
    search_docs = []
    for i, chunk in enumerate(chunks):
        vector = openai_client.get_embedding(chunk)
        search_docs.append({
            "id": f"{doc_id}_{i}",
            "document_id": doc_id,
            "document_name": file_name,
            "content": chunk,
            "content_vector": vector,
        })
    search_client.upsert_chunks(search_docs)

    # 6. Save metadata to Cosmos DB
    metadata = {
        "id": doc_id,
        "name": file_name,
        "size": len(raw_bytes),
        "chunks": len(chunks),
        "status": "indexed",
    }
    cosmos_client.save_document_metadata(metadata)

    logger.info("Ingested document %s (%d chunks)", file_name, len(chunks))
    return func.HttpResponse(
        json.dumps(metadata),
        mimetype="application/json",
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Query the knowledge base
# ---------------------------------------------------------------------------

@app.route(route="query", methods=["POST"])
def query(req: func.HttpRequest) -> func.HttpResponse:
    body = req.get_json()
    question = (body or {}).get("question", "").strip()
    if not question:
        return func.HttpResponse(
            json.dumps({"error": "Field 'question' is required."}),
            mimetype="application/json",
            status_code=400,
        )

    # 1. Embed the question
    query_vector = openai_client.get_embedding(question)

    # 2. Retrieve top-k relevant chunks
    hits = search_client.vector_search(query_vector, top_k=5)

    # 3. Build context string
    context = "\n\n---\n\n".join(
        f"[{h['document_name']}]\n{h['content']}" for h in hits
    )

    # 4. Generate grounded answer
    user_message = f"Context:\n{context}\n\nQuestion: {question}"
    answer = openai_client.chat_completion(SYSTEM_PROMPT, user_message)

    sources = [{"document": h["document_name"], "chunk": h["content"][:300]} for h in hits]

    return func.HttpResponse(
        json.dumps({"answer": answer, "sources": sources}),
        mimetype="application/json",
        status_code=200,
    )


# ---------------------------------------------------------------------------
# List documents
# ---------------------------------------------------------------------------

@app.route(route="documents", methods=["GET"])
def list_documents(req: func.HttpRequest) -> func.HttpResponse:
    docs = cosmos_client.list_documents()
    return func.HttpResponse(
        json.dumps({"documents": docs}),
        mimetype="application/json",
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(file_name: str, data: bytes) -> str:
    if file_name.lower().endswith(".pdf"):
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    # Plain text / fallback
    return data.decode("utf-8", errors="replace")


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping token-aware chunks."""
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]
