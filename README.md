# LayaKBTest — RAG Knowledge Base

A full-stack Retrieval-Augmented Generation (RAG) application for insurance documents. Upload PDFs and Excel files, then ask questions and receive AI-grounded answers with source citations.

## Architecture

```
Browser (React + Vite)
  │   Azure Static Web Apps
  │   https://mango-moss-0bbb26d0f.7.azurestaticapps.net
  │
  │  HTTP /api/*  (VITE_API_BASE_URL)
  ▼
FastAPI (Python 3.12, Docker)
  │   Azure Container Apps — scales to zero
  │   https://ca-layakbtest-dev.orangemushroom-0c15fa01.eastus.azurecontainerapps.io
  │
  ├── POST /api/ingest  ──► Azure Blob Storage   (raw files)
  │                    ──► Ark Embedding API     (chunk vectors)
  │                    ──► Azure AI Search       (vector index)
  │                    ──► Cosmos DB             (metadata)
  │
  └── POST /api/query  ──► Ark Embedding API     (query vector)
                       ──► Azure AI Search       (hybrid search)
                       ──► Ark Chat API          (grounded answer)
                       ◄── answer + source citations
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript (Vite 5) |
| Backend | Python 3.12, FastAPI + Uvicorn |
| Containerisation | Docker → Azure Container Registry |
| Hosting (backend) | Azure Container Apps (Consumption, min 0 replicas) |
| Hosting (frontend) | Azure Static Web Apps (Free tier) |
| Vector Search | Azure AI Search (free SKU, hybrid + semantic) |
| LLM / Embeddings | Ark API — `glm-5.2` chat, `doubao-embedding-vision` embeddings |
| Document Storage | Azure Blob Storage (Standard LRS) |
| Metadata | Azure Cosmos DB (Serverless, SQL API) |
| IaC | Terraform (`azurerm ~> 4.0`) — local state |

## Live URLs

| Service | URL |
|---------|-----|
| Frontend | https://mango-moss-0bbb26d0f.7.azurestaticapps.net |
| Backend health | https://ca-layakbtest-dev.orangemushroom-0c15fa01.eastus.azurecontainerapps.io/api/health |

---

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker (optional, for container testing)
- Azure CLI (`az login` already done)

### 1. Copy and fill environment file

```bash
cp .env.example .env
# Edit .env and fill in values from your Azure deployment
# Run `cd infra && terraform output` to retrieve all endpoints/keys
```

### 2. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Load env and run
source ../.env                   # Windows: use dotenv or set manually
uvicorn main:app --reload --port 8000
```

Backend is available at `http://localhost:8000`. FastAPI docs at `http://localhost:8000/docs`.

### 3. Start the frontend

```bash
cd frontend
npm install
# Point frontend at local backend:
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev
```

Frontend is available at `http://localhost:5173`.

---

## API Reference

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/health` | Health check — returns `{"status":"ok"}` |
| `POST` | `/api/ingest` | Upload and index a document |
| `POST` | `/api/query` | Ask a question (standard RAG) |
| `GET` | `/api/documents` | List all indexed documents |
| `POST` | `/api/agent_query` | Ask a question (agentic RAG with tool calls) |
| `POST` | `/api/setup_indexer` | Create/reset the AI Search indexer pipeline |
| `POST` | `/api/excel_skill` | Custom skill endpoint for AI Search Excel parsing |
| `POST` | `/api/clean_document` | Custom skill endpoint for document cleaning |

### POST /api/ingest

```
Content-Type: multipart/form-data
Field: file  (PDF or Excel)
```

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "policy.pdf",
  "chunks": 42,
  "status": "indexed"
}
```

### POST /api/query

```json
// Request
{ "question": "What is the annual deductible?" }

// Response
{
  "answer": "The annual deductible is ¥5,000...",
  "sources": [
    { "document": "policy.pdf", "chunk": "...relevant excerpt (first 300 chars)..." }
  ]
}
```

### GET /api/documents

```json
{
  "documents": [
    { "id": "...", "name": "policy.pdf", "size": 204800, "chunks": 42, "status": "indexed", "_ts": 1721779200 }
  ]
}
```

---

## Environment Variables

Copy `.env.example` to `.env` for local development. All values can be read from `terraform output` after provisioning.

| Variable | Description |
|----------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Blob Storage connection string |
| `AZURE_STORAGE_CONTAINER_NAME` | Blob container name (default: `documents`) |
| `AZURE_SEARCH_ENDPOINT` | AI Search service URL |
| `AZURE_SEARCH_API_KEY` | AI Search admin key |
| `AZURE_SEARCH_INDEX_NAME` | Search index name (default: `knowledge-base`) |
| `AZURE_COSMOS_ENDPOINT` | Cosmos DB account URL |
| `AZURE_COSMOS_KEY` | Cosmos DB primary key |
| `AZURE_COSMOS_DATABASE` | Database name (default: `layakbtest`) |
| `AZURE_COSMOS_CONTAINER` | Container name (default: `documents`) |
| `ARK_API_KEY` | Ark (ByteDance/Volcengine) API key |
| `ARK_BASE_URL` | Ark API base URL (default: `https://ark.cn-beijing.volces.com/api/v3`) |
| `ARK_CHAT_MODEL` | Chat model ID (default: `glm-5.2`) |
| `ARK_EMBEDDING_MODEL` | Embedding model ID (default: `doubao-embedding-vision`) |

---

## Infrastructure

All Azure resources are managed with Terraform (local state in `infra/terraform.tfstate`).

```bash
cd infra
terraform init        # first time only
terraform plan
terraform apply
terraform output      # print all endpoints and keys
```

### Deployed Resources

| Resource | Name | SKU/Tier |
|----------|------|----------|
| Resource Group | `rg-layakbtest-dev` | — |
| Storage Account | `stlayakbtestyoj8gp` | Standard LRS |
| Container Registry | `crlayakbtestyoj8gp` | Basic |
| Container App Environment | `cae-layakbtest-dev` | Consumption |
| Container App (API) | `ca-layakbtest-dev` | 0.25 CPU / 0.5 Gi |
| AI Search | `srch-layakbtest-dev-yoj8gp` | Free |
| Cosmos DB | `cosmos-layakbtest-dev-yoj8gp` | Serverless |
| Static Web App | `swa-layakbtest-dev` | Free |

---

## Deployment

Use `scripts/deploy.sh` for manual deployments.

```bash
# Deploy backend only
./scripts/deploy.sh backend

# Deploy frontend only
./scripts/deploy.sh frontend

# Deploy both
./scripts/deploy.sh all
```

The script reads Azure resource names and URLs from `terraform output`, so always run from the repo root after `terraform apply`.

---

## Project Structure

```
LayaKBTest/
├── frontend/                  # React + TypeScript (Vite)
│   ├── src/
│   │   ├── api/client.ts      # Axios API client
│   │   ├── components/        # DocumentUpload, SourceCard
│   │   └── pages/             # ChatPage, DocumentsPage
│   ├── staticwebapp.config.json
│   └── package.json
├── backend/                   # FastAPI (Python 3.12)
│   ├── main.py                # All API endpoints
│   ├── shared/                # Azure service clients
│   │   ├── openai_client.py   # Ark API (chat + embeddings)
│   │   ├── search_client.py   # Azure AI Search
│   │   ├── blob_client.py     # Azure Blob Storage
│   │   ├── cosmos_client.py   # Azure Cosmos DB
│   │   └── indexer_setup.py   # AI Search indexer pipeline
│   ├── Dockerfile
│   └── requirements.txt
├── infra/                     # Terraform
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── backend.tf             # Local state
├── scripts/
│   └── deploy.sh              # Deployment script
└── .env.example
```
