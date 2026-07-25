import io
import json
import logging
import os
import uuid

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List

from shared import blob_client, search_client, openai_client, cosmos_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LayaKB API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """You are a helpful assistant that answers questions based solely on the provided context.
If the answer is not found in the context, say "I don't have enough information to answer that."
Always cite the source document(s) you used."""

_AGENT_SYSTEM_PROMPT = """You are an expert insurance advisor with access to a health and medical insurance knowledge base.
Answer questions accurately based on policy documents.

Rules:
1. Always use the search_knowledge_base tool to find relevant policy information before answering.
2. If asked about a specific document, use generate_sas_url to provide a download link.
3. Be precise with coverage amounts, percentages, deductibles, and policy terms.
4. If information is not found in the knowledge base, clearly state that.
5. Always end your response with a Reference section listing all sources used.

Response format (always end with this):
---
Reference: {source_file_name} (Page {page_number} or Sheet: {sheet_name})
Link: {sas_url} (valid for 24 hours)
"""

_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search the insurance knowledge base using hybrid search (vector + keyword + semantic reranker).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "doc_type": {"type": "string", "enum": ["pdf", "excel", "word", ""]},
                    "product_name": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_sas_url",
            "description": "Generate a time-limited SAS URL for a Blob Storage file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "blob_path": {"type": "string"},
                    "expiry_hours": {"type": "integer", "default": 24},
                },
                "required": ["blob_path"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Ingest helpers
# ---------------------------------------------------------------------------

def _index_document(doc_id: str, file_name: str, raw_bytes: bytes):
    """Background task: embed and index a document already uploaded to blob."""
    try:
        text = _extract_text(file_name, raw_bytes)
        chunks = _chunk_text(text)

        search_client.ensure_index()

        search_docs = []
        for i, chunk in enumerate(chunks):
            vector = openai_client.get_embedding(chunk)
            search_docs.append({
                "id": f"{doc_id}_{i}",
                "document_id": doc_id,
                "source_file_name": file_name,
                "content": chunk,
                "content_vector": vector,
            })
        search_client.upsert_chunks(search_docs)

        cosmos_client.update_document_status(doc_id, status="indexed", chunks=len(chunks))
        logger.info("Indexed document %s (%d chunks)", file_name, len(chunks))
    except Exception:
        logger.exception("Failed to index document %s", file_name)
        cosmos_client.update_document_status(doc_id, status="failed")


# ---------------------------------------------------------------------------
# Ingest a single document (async)
# ---------------------------------------------------------------------------

@app.post("/api/ingest")
async def ingest(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    doc_id = str(uuid.uuid4())
    file_name = file.filename or f"{doc_id}.bin"
    raw_bytes = await file.read()

    blob_client.upload_document(file_name, raw_bytes)

    metadata = {
        "id": doc_id,
        "name": file_name,
        "size": len(raw_bytes),
        "chunks": 0,
        "status": "processing",
    }
    cosmos_client.save_document_metadata(metadata)

    background_tasks.add_task(_index_document, doc_id, file_name, raw_bytes)

    logger.info("Accepted document %s for async indexing", file_name)
    return JSONResponse(content=metadata)


# ---------------------------------------------------------------------------
# Batch ingest (async)
# ---------------------------------------------------------------------------

@app.post("/api/ingest/batch")
async def ingest_batch(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        doc_id = str(uuid.uuid4())
        file_name = file.filename or f"{doc_id}.bin"
        raw_bytes = await file.read()

        blob_client.upload_document(file_name, raw_bytes)

        metadata = {
            "id": doc_id,
            "name": file_name,
            "size": len(raw_bytes),
            "chunks": 0,
            "status": "processing",
        }
        cosmos_client.save_document_metadata(metadata)
        background_tasks.add_task(_index_document, doc_id, file_name, raw_bytes)
        results.append(metadata)
        logger.info("Accepted document %s for async indexing", file_name)

    return JSONResponse(content={"documents": results})


# ---------------------------------------------------------------------------
# Query the knowledge base
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str


@app.post("/api/query")
def query(body: QueryRequest):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Field 'question' is required.")

    query_vector = openai_client.get_embedding(question)
    hits = search_client.vector_search(query_vector, top_k=5)

    context = "\n\n---\n\n".join(
        f"[{h['source_file_name']}]\n{h['content']}" for h in hits
    )
    user_message = f"Context:\n{context}\n\nQuestion: {question}"
    answer = openai_client.chat_completion(SYSTEM_PROMPT, user_message)

    sources = [{"document": h["source_file_name"], "chunk": h["content"][:300]} for h in hits]
    return {"answer": answer, "sources": sources}


# ---------------------------------------------------------------------------
# List documents
# ---------------------------------------------------------------------------

@app.get("/api/documents")
def list_documents():
    docs = cosmos_client.list_documents()
    return {"documents": docs}


# ---------------------------------------------------------------------------
# Excel Custom Skill — called by AI Search Indexer
# ---------------------------------------------------------------------------

@app.post("/api/excel_skill")
async def excel_skill(request_body: dict):
    results = []
    for record in request_body.get("values", []):
        try:
            data = record.get("data", {})
            source_blob_path = data.get("source_blob_path", "")
            source_file_name = data.get("source_file_name", "")
            blob_name = _strip_container_prefix(source_blob_path)
            raw_bytes = blob_client.download_document_by_path(blob_name)
            rows = _parse_excel(raw_bytes, source_blob_path, source_file_name)
            results.append({
                "recordId": record["recordId"],
                "data": {"excel_rows": rows},
                "errors": [],
                "warnings": [],
            })
        except Exception as exc:
            logger.exception("excel_skill failed for record %s", record.get("recordId"))
            results.append({
                "recordId": record["recordId"],
                "data": {"excel_rows": []},
                "errors": [{"message": str(exc)}],
                "warnings": [],
            })
    return {"values": results}


# ---------------------------------------------------------------------------
# Data Cleaning Custom Skill — called by AI Search Indexer
# ---------------------------------------------------------------------------

@app.post("/api/clean_document")
async def clean_document(request_body: dict):
    results = []
    for record in request_body.get("values", []):
        try:
            data = record.get("data", {})
            content = data.get("content", "") or ""
            doc_type = (data.get("doc_type", "") or "").lower()

            if "excel" in doc_type:
                cleaned, notes = _clean_excel_row(content)
            else:
                cleaned, notes = _clean_document_text(content)

            results.append({
                "recordId": record["recordId"],
                "data": {
                    "cleaned_content": cleaned,
                    "cleaning_notes": ", ".join(notes),
                },
                "errors": [],
                "warnings": [],
            })
        except Exception as exc:
            results.append({
                "recordId": record["recordId"],
                "data": {"cleaned_content": content, "cleaning_notes": f"error: {exc}"},
                "errors": [{"message": str(exc)}],
                "warnings": [],
            })
    return {"values": results}


# ---------------------------------------------------------------------------
# Agent Query
# ---------------------------------------------------------------------------

@app.post("/api/agent_query")
def agent_query(body: QueryRequest):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Field 'question' is required.")

    messages = [
        {"role": "system", "content": _AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for _ in range(6):
        choice = openai_client.chat_with_tools(messages, _AGENT_TOOLS)

        if choice.finish_reason == "tool_calls":
            messages.append(choice.message.model_dump())
            for tc in choice.message.tool_calls:
                result = _execute_agent_tool(tc)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })
        else:
            return {"answer": choice.message.content or ""}

    raise HTTPException(status_code=500, detail="Agent did not converge within iteration limit.")


# ---------------------------------------------------------------------------
# Setup Indexer
# ---------------------------------------------------------------------------

@app.post("/api/setup_indexer")
def setup_indexer():
    from shared.indexer_setup import setup_indexer_pipeline
    try:
        search_client.ensure_index()
        setup_indexer_pipeline()
        return {"status": "Index and indexer pipeline created and started"}
    except Exception as exc:
        logger.exception("Failed to setup indexer pipeline")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(file_name: str, data: bytes) -> str:
    if file_name.lower().endswith(".pdf"):
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return data.decode("utf-8", errors="replace")


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunks.append(enc.decode(tokens[start:end]))
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]


def _strip_container_prefix(blob_path: str) -> str:
    import re
    container = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "")
    blob_path = re.sub(r"^https?://[^/]+/[^/]+/", "", blob_path)
    if blob_path.startswith(container + "/"):
        blob_path = blob_path[len(container) + 1:]
    return blob_path


def _parse_excel(raw_bytes: bytes, blob_path: str, file_name: str) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)
    rows = []
    for sheet in wb.worksheets:
        _unmerge_cells(sheet)
        data = [r for r in sheet.iter_rows(values_only=True) if any(v is not None for v in r)]
        if len(data) < 2:
            continue
        headers, data_start = _detect_headers(data)
        for row in data[data_start:]:
            sentence = _row_to_sentence(headers, row, sheet.title)
            if not sentence:
                continue
            rows.append({
                "content": sentence,
                "source_blob_path": blob_path,
                "source_file_name": file_name,
                "sheet_name": sheet.title,
                "doc_type": "excel",
                "product_name": _extract_product_name(sentence),
            })
    return rows


def _unmerge_cells(sheet):
    for rng in list(sheet.merged_cells.ranges):
        value = sheet.cell(rng.min_row, rng.min_col).value
        sheet.unmerge_cells(str(rng))
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                sheet.cell(r, c).value = value


def _detect_headers(data: list) -> tuple[list[str], int]:
    def all_strings(row):
        return all(v is None or isinstance(v, str) for v in row) and any(v for v in row)

    if len(data) >= 2 and all_strings(data[0]) and all_strings(data[1]):
        headers = []
        for h1, h2 in zip(data[0], data[1]):
            h1 = str(h1).strip() if h1 else ""
            h2 = str(h2).strip() if h2 else ""
            headers.append(f"{h1} - {h2}" if h1 and h2 and h1 != h2 else h1 or h2)
        return headers, 2

    if all_strings(data[0]):
        return [str(h).strip() if h else "" for h in data[0]], 1

    from openpyxl.utils import get_column_letter
    return [get_column_letter(i + 1) for i in range(len(data[0]))], 0


def _row_to_sentence(headers: list[str], row: tuple, sheet_name: str) -> str:
    parts = []
    for h, v in zip(headers, row):
        if v is None or str(v).strip() == "":
            continue
        parts.append(f"{h.strip()}: {str(v).strip()}" if h.strip() else str(v).strip())
    if not parts:
        return ""
    return f"[{sheet_name}] " + ", ".join(parts) + "."


def _extract_product_name(text: str) -> str:
    import re
    m = re.search(r"(?i)([\w\s]*(medical|health|insurance|plan|policy|coverage)[\w\s]*)", text)
    return m.group(1).strip()[:100] if m else ""


def _clean_document_text(text: str) -> tuple[str, list[str]]:
    import re
    notes = []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    before = len(text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    if len(text) < before:
        notes.append("removed_control_chars")
    for p in [r"(?im)^\s*CONFIDENTIAL\s*$", r"(?im)^\s*DRAFT\s*$", r"(?im)^\s*WATERMARK\s*$"]:
        if re.search(p, text):
            text = re.sub(p, "", text)
            notes.append("removed_watermark")
    text = _remove_doc_headers_footers(text, notes)
    toc_lines = [l for l in text.split("\n") if re.match(r".{5,}\s+\.{3,}\s*\d+\s*$", l)]
    if len(toc_lines) > 5:
        text = re.sub(r"(?m)^.{5,}\s+\.{3,}\s*\d+\s*$", "", text)
        notes.append("removed_toc")
    text = re.sub(r"(?m)^((?:Article|Section|Clause|第)\s*\d+[\.\d]*)\s*\n+", r"\1 ", text)
    notes.append("reassociated_clauses")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), notes


def _remove_doc_headers_footers(text: str, notes: list[str]) -> str:
    import re
    from collections import Counter
    _NOISE = [
        r"(?i)^\s*page\s+\d+\s*(of\s+\d+)?\s*$",
        r"^\s*-\s*\d+\s*-\s*$",
        r"^\s*\d+\s*$",
        r"(?i)^\s*(all rights reserved|copyright\s+\d{4})\s*$",
    ]
    lines = text.split("\n")
    lines = [l for l in lines if not any(re.match(p, l) for p in _NOISE)]
    counts = Counter(l.strip() for l in lines if l.strip())
    repeated = {s for s, n in counts.items() if n >= 3 and len(s) < 200}
    if repeated:
        lines = [l for l in lines if l.strip() not in repeated]
        notes.append("removed_repeated_header_footer")
    return "\n".join(lines)


def _clean_excel_row(content: str) -> tuple[str, list[str]]:
    import re
    notes = []
    if not content or not content.strip():
        return "", ["empty_record"]
    content = content.strip()
    content = re.sub(r"[¥$€£]\s*", "", content)
    content = re.sub(r"(\d)\s*,\s*(\d{3})", r"\1\2", content)
    notes.append("normalized_numerics")
    if re.match(r"^[\s\-_=|/\\]+$", content):
        return "", ["formatting_only"]
    return content.strip(), notes


def _execute_agent_tool(tool_call) -> dict:
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments or "{}")

    if name == "search_knowledge_base":
        query = args.get("query", "")
        doc_type = args.get("doc_type", "")
        product_name = args.get("product_name", "")
        query_vector = openai_client.get_embedding(query)
        filter_parts = []
        if doc_type:
            filter_parts.append(f"doc_type eq '{doc_type}'")
        if product_name:
            filter_parts.append(f"product_name eq '{product_name}'")
        filter_expr = " and ".join(filter_parts) if filter_parts else None
        hits = search_client.hybrid_search(query, query_vector, top_k=5, filter_expr=filter_expr)
        return {"results": hits}

    if name == "generate_sas_url":
        raw_path = args.get("blob_path", "")
        expiry_hours = int(args.get("expiry_hours", 24))
        blob_name = _strip_container_prefix(raw_path)
        sas_url = blob_client.generate_sas_url(blob_name, expiry_hours)
        return {"sas_url": sas_url, "blob_path": blob_name}

    return {"error": f"Unknown tool: {name}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
