# Langfuse Setup Guide for LayaKBTest

Step-by-step guide to get Langfuse tracing, prompt management, and evaluation running for this project.

---

## Prerequisites

- Python 3.13+
- The backend dependencies already installed: `pip install -r backend/requirements.txt`
- A running backend (local or deployed) if you want to verify end-to-end tracing

---

## Step 1: Create a Langfuse Project

### Option A: Langfuse Cloud (recommended)

1. Go to https://cloud.langfuse.com and sign up.
2. Create a new project (e.g. `layakbtest`).
3. Go to **Project Settings → API Keys**.
4. Copy the **Public Key** (`pk-lf-...`) and **Secret Key** (`sk-lf-...`).

### Option B: Self-Hosted

1. Deploy Langfuse via Docker: https://langfuse.com/docs/deployment/docker
2. Use your own host URL (e.g. `http://localhost:3000`) instead of `https://cloud.langfuse.com`.
3. Create a project and copy the API keys from the UI.

---

## Step 2: Configure Environment Variables

Add these to your `.env` file (copy from `.env.example`):

```bash
# ── Langfuse ──
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_ENVIRONMENT=dev
LANGFUSE_PROMPT_CACHE_TTL=300
LANGFUSE_JUDGE_TIMEOUT_SECONDS=30
```

**Field reference:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LANGFUSE_PUBLIC_KEY` | Yes | — | Project public key from Langfuse UI |
| `LANGFUSE_SECRET_KEY` | Yes | — | Project secret key from Langfuse UI |
| `LANGFUSE_HOST` | No | `https://cloud.langfuse.com` | Cloud or self-hosted URL |
| `LANGFUSE_ENVIRONMENT` | No | `dev` | `dev` / `staging` / `prod` — drives prompt resolution |
| `LANGFUSE_PROMPT_CACHE_TTL` | No | `300` | In-memory prompt cache TTL in seconds |
| `LANGFUSE_JUDGE_TIMEOUT_SECONDS` | No | `30` | Judge LLM call timeout |

> **Note:** If these variables are missing, the API still works — tracing becomes a no-op and prompts fall back to hardcoded text. This is intentional for local dev without keys.

---

## Step 3: Verify Dependencies

```bash
cd /opt/data/LayaKBTest
pip install -r backend/requirements.txt
```

Confirm the Langfuse SDK is installed:

```bash
python -c "import langfuse; print(langfuse.__version__)"
```

---

## Step 4: Seed Prompts into Langfuse

`backend/main.py` no longer hardcodes system prompts. They are fetched from Langfuse Prompt Management at runtime. You need to upload them once.

Run this from the `backend/` directory:

```bash
cd backend
python -c "
import langfuse_prompts as lp

lp.create_or_update_prompt(
    lp.SYSTEM_PROMPT_NAME,
    lp.FALLBACK_PROMPTS[lp.SYSTEM_PROMPT_NAME],
    environment='dev',
)
lp.create_or_update_prompt(
    lp.AGENT_SYSTEM_PROMPT_NAME,
    lp.FALLBACK_PROMPTS[lp.AGENT_SYSTEM_PROMPT_NAME],
    environment='dev',
)
print('Prompts seeded successfully')
"
```

**What this does:**
- Creates `system_prompt` and `agent_system_prompt` in your Langfuse project
- Labels both as `dev` so `get_prompt(..., environment="dev")` resolves them
- If they already exist, it creates a new version — prompts are immutable per version

**Promote to staging/prod later:**

```python
lp.create_or_update_prompt(lp.SYSTEM_PROMPT_NAME, "...text...", environment="staging")
```

---

## Step 5: Smoke Test

### 5.1 Test prompt fetching

```bash
cd backend
python -c "
import langfuse_prompts as lp
p = lp.get_prompt(lp.SYSTEM_PROMPT_NAME, environment='dev')
print('Prompt fetched OK, length:', len(p))
"
```

Expected: prints prompt length (~1,500 chars). If Langfuse is unreachable, it falls back to hardcoded text and still prints a length.

### 5.2 Test tracing

Start the backend:

```bash
cd backend
python main.py
```

In another terminal, send a request:

```bash
curl -X POST http://localhost:8000/api/agent_query \
  -H "Content-Type: application/json" \
  -H "X-Function-Instance-Id: test-001" \
  -d '{"question": "What is the excess on travel insurance?"}'
```

Then check the Langfuse UI → **Traces** — you should see a trace named `api_agent_query` with nested spans for the agent loop, tool calls, and LLM calls.

### 5.3 Test the judge (optional)

```bash
cd backend
python -c "
from langfuse_judge import judge_trace
result = judge_trace(
    trace_id='test-trace-001',
    question='What is the excess?',
    answer='The excess is €200 per claim.',
    key_points=['excess is €200'],
)
print('Pass:', result['pass'])
print('Coverage:', result['coverage_rate'])
"
```

Expected: `Pass: True`, `Coverage: 1.0` (or similar).

---

## Step 6: Verify CI Integration (optional)

The repo includes `.github/workflows/langfuse-regression.yml`. To make it work in GitHub Actions:

1. Go to your repo → **Settings → Secrets and variables → Actions**.
2. Add these repository secrets:
   - `LANGFUSE_PUBLIC_KEY`
   - `LANGFUSE_SECRET_KEY`
   - `ARK_API_KEY`
   - `ARK_CHAT_MODEL`
   - `ARK_EMBEDDING_MODEL`
3. Push to `main` or open a PR — the workflow will run offline batch eval and upload the report.

---

## Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Traces don't appear in Langfuse UI | Keys missing or process exited too fast | Check `.env`, add `flush_langfuse()` before exit |
| Prompts still use hardcoded text | Not seeded yet or cache stale | Run seed script, or call `lp.clear_cache()` |
| Judge returns `"timeout"` | Judge LLM too slow | Increase `LANGFUSE_JUDGE_TIMEOUT_SECONDS` |
| Offline eval runs locally but no Dataset in UI | Keys missing | Set `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` |

---

## Next Steps

- **Tracing:** Every `/api/query` and `/api/agent_query` call is automatically traced. Open the Langfuse UI to inspect spans.
- **Prompt editing:** Edit prompts in the Langfuse UI → new versions are created automatically. Use `rollback_prompt()` to revert.
- **Evaluation:** Run `python -m backend.langfuse_offline_eval --dataset smoke-test --output report.json` for a full regression batch.
- **Full docs:** See `INTEGRATION.md` for advanced usage, CI configuration, and troubleshooting.
