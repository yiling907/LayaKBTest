# LayaKBTest — RAG Knowledge Base

A full-stack Retrieval-Augmented Generation (RAG) application. Upload documents, ask questions, and receive AI-grounded answers with source citations.

## Architecture

```
Browser (React)
     │
     │  HTTP /api/*
     ▼
Azure Functions (Python 3.14)
     ├── POST /api/ingest  ──► Azure Blob Storage (raw docs)
     │                    ──► Azure OpenAI (embeddings)
     │                    ──► Azure AI Search (vector index)
     │                    ──► Cosmos DB (metadata)
     │
     └── POST /api/query  ──► Azure OpenAI (query embedding)
                          ──► Azure AI Search (vector search)
                          ──► Azure OpenAI (chat completion + grounding)
                          ◄── answer + source citations
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + TypeScript (Vite) |
| Backend | Python 3.14, Azure App Functions v2 |
| Vector Search | Azure AI Search (semantic + vector) |
| AI | Azure OpenAI — `gpt-4o` + `text-embedding-ada-002` |
| Document Storage | Azure Blob Storage |
| Metadata | Azure Cosmos DB (serverless, SQL API) |
| IaC | Terraform (`azurerm ~> 4.0`) |
| CI/CD | GitHub Actions |

## Prerequisites

- [Node.js](https://nodejs.org/) >= 20
- [Python](https://www.python.org/) 3.14
- [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local) v4
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) — run `az login`
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.9

## Getting Started

### 1. Provision Infrastructure

```bash
cd infra

# First-time: create remote state storage manually (or use local state for dev)
# Then:
terraform init
terraform apply -var="environment=dev"
```

Copy the outputs (Function App URL, AI Search endpoint, etc.) into your `.env` / `local.settings.json`.

### 2. Backend (local)

```bash
cd backend
cp ../.env.example local.settings.json
# Edit local.settings.json and fill in your Azure service values

pip install -r requirements.txt
func start
# Functions available at http://localhost:7071
```

### 3. Frontend (local)

```bash
cd frontend
npm install
npm run dev
# App available at http://localhost:5173
```

## API Reference

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/ingest` | Upload and index a document (multipart/form-data, field: `file`) |
| `POST` | `/api/query` | Ask a question — returns `{ answer, sources }` |
| `GET` | `/api/documents` | List all indexed documents |

### POST /api/ingest

```json
// Request: multipart/form-data with field "file"
// Response:
{
  "id": "doc_abc123",
  "name": "my-document.pdf",
  "chunks": 42,
  "status": "indexed"
}
```

### POST /api/query

```json
// Request:
{ "question": "What is the refund policy?" }

// Response:
{
  "answer": "The refund policy allows returns within 30 days...",
  "sources": [
    { "document": "policy.pdf", "chunk": "...relevant excerpt..." }
  ]
}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Blob Storage connection string |
| `AZURE_STORAGE_CONTAINER_NAME` | Container name for uploaded documents |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search service URL |
| `AZURE_SEARCH_API_KEY` | Azure AI Search admin key |
| `AZURE_SEARCH_INDEX_NAME` | Name of the search index |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource URL |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | API version (e.g. `2024-02-01`) |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding model deployment name |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Chat model deployment name |
| `AZURE_COSMOS_ENDPOINT` | Cosmos DB account URL |
| `AZURE_COSMOS_KEY` | Cosmos DB primary key |
| `AZURE_COSMOS_DATABASE` | Database name |
| `AZURE_COSMOS_CONTAINER` | Container name for document metadata |

See `.env.example` for a full template.

## Deployment

CI/CD is handled via GitHub Actions:

- **Push to `main`** → deploys backend to Azure Functions and frontend to Azure Static Web Apps
- **PR opened** → runs `terraform plan` and posts the output as a PR comment
- **Merge to `main`** → runs `terraform apply`

### Required GitHub Secrets

| Secret | Value |
|--------|-------|
| `AZURE_CREDENTIALS` | Output of `az ad sp create-for-rbac --sdk-auth` |
| `AZURE_FUNCTIONAPP_NAME` | Your Function App name |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | Deployment token from Azure Static Web Apps |

## Project Structure

```
LayaKBTest/
├── frontend/          # React + TypeScript (Vite)
├── backend/           # Azure Functions (Python 3.14)
├── infra/             # Terraform
├── .github/workflows/ # CI/CD
├── .env.example       # Environment variable template
└── README.md
```

## Contributing

1. Create a feature branch: `git checkout -b feat/your-feature`
2. Make changes and add tests
3. Run `pytest` (backend) and `npm test` (frontend) — all must pass
4. Open a PR — Terraform plan will run automatically
