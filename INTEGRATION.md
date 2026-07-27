# Langfuse Integration Guide

Practical setup and operation notes for the Langfuse integration in this repo:
tracing (`backend/langfuse_tracing.py`), prompt management
(`backend/langfuse_prompts.py`), online LLM-as-judge evaluation
(`backend/langfuse_judge.py`), and offline batch evaluation
(`backend/langfuse_offline_eval.py`).

## 1. Setup

1. Create a Langfuse account and project:
   - Cloud: https://cloud.langfuse.com — sign up, create a project, and copy
     the project's public/secret API keys from **Settings → API Keys**.
   - Self-hosted: deploy Langfuse (see langfuse/langfuse on GitHub) and use
     your own host URL instead of `https://cloud.langfuse.com`.
2. Set environment variables (see `.env.example` for the full template):

   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com   # or your self-hosted URL
   LANGFUSE_ENVIRONMENT=dev                   # dev | staging | prod
   LANGFUSE_PROMPT_CACHE_TTL=300              # seconds
   LANGFUSE_JUDGE_TIMEOUT_SECONDS=30
   ```

3. Every module in this integration degrades to a no-op (tracing) or a
   hardcoded fallback (prompts) if these keys are absent — the API keeps
   serving answers even without Langfuse configured. This means local dev
   and CI both work without keys; you only need real keys to see traces,
   prompt versions, and evaluation runs in the Langfuse UI.

## 2. Prompt Migration

`backend/main.py` used to hardcode `SYSTEM_PROMPT` and `_AGENT_SYSTEM_PROMPT`.
They now come from `langfuse_prompts.get_prompt(...)`, which fetches from
Langfuse Prompt Management and falls back to `FALLBACK_PROMPTS` (the original
hardcoded text) if the prompt hasn't been created yet or Langfuse is
unreachable.

To seed Langfuse with the two prompts for the first time, run this once
(from `backend/`, with `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` set):

```python
import langfuse_prompts as lp

lp.create_or_update_prompt(
    lp.SYSTEM_PROMPT_NAME,
    lp.FALLBACK_PROMPTS[lp.SYSTEM_PROMPT_NAME],
    environment="dev",
)
lp.create_or_update_prompt(
    lp.AGENT_SYSTEM_PROMPT_NAME,
    lp.FALLBACK_PROMPTS[lp.AGENT_SYSTEM_PROMPT_NAME],
    environment="dev",
)
```

This creates version 1 of both `system_prompt` and `agent_system_prompt` in
Langfuse and labels them `dev`. Repeat with `environment="staging"` /
`"prod"` once you're ready to promote — labels are how `get_prompt(name,
environment=..., version="latest")` resolves which version to serve.

**Editing a prompt afterwards:** edit it directly in the Langfuse UI (Prompts
→ select prompt → new version), or call `create_or_update_prompt` again with
new text — either creates a new immutable version. Label it for the
environment you want to serve it from.

**Rollback:** call `langfuse_prompts.rollback_prompt(name, target_version,
environment)` to re-point an environment's label back to an older version.
Because prompt versions are immutable, this is the only way to "undo" a bad
prompt edit — it's a label move, not a content revert.

**Cache:** prompt text is cached in-memory per `(name, environment, version)`
for `LANGFUSE_PROMPT_CACHE_TTL` seconds (default 300). Call
`langfuse_prompts.clear_cache()` if you need a fetched change to show up
immediately (mostly useful in tests).

## 3. Online Judge

`langfuse_judge.judge_trace(trace_id, question, answer, key_points,
conversation_history=None, tool_calls=None)` evaluates one agent response on
exactly two dimensions — no BLEU/ROUGE/BERTScore:

1. Coverage of the mandatory `key_points` you pass in.
2. Violations of the fixed `RED_LINES` list (fabrication, non-compliant
   recommendation, contradiction, data leak, redundant tool calls).

Call it manually against any trace, e.g. right after `/api/agent_query`
returns:

```python
from langfuse_judge import judge_trace

result = judge_trace(
    trace_id=trace_id,          # from langfuse_tracing.get_langfuse_client().get_current_trace_id()
    question=question,
    answer=answer,
    key_points=["excess is €200", "covers Europe only"],
    tool_calls=["get_user_policies", "search_knowledge_base"],
)
print(result["pass"], result["coverage_rate"], result["red_line_violations"])
```

**Where scores show up:** `judge_trace` writes two scores back onto the
Langfuse trace via `client.create_score(...)`:
- `business_judge_pass` (BOOLEAN, or a CATEGORICAL `"timeout"`/`"error"` on
  failure) with the judge's comment attached.
- `key_point_coverage_rate` (NUMERIC, 0.0–1.0).

Open the trace in the Langfuse UI — the **Scores** panel on the trace detail
page shows both, and the Traces table can be filtered/sorted by score name.

## 4. Offline Batch Experiment

`backend/langfuse_offline_eval.py` auto-generates 30–50 test queries from the
business content in `backend/data/` (any PDF/TXT/MD/DOCX policy documents
found there, plus the structured `users.json` business data), runs each
through the agent, judges the response, and exports a regression report.

**CLI:**

```bash
cd /path/to/repo
python -m backend.langfuse_offline_eval \
  --dataset laya-regression-2026-07-26 \
  --output report.json \
  --target-count 40          # optional, clamped to [30, 50]
  # --base-url http://localhost:8000   # optional: hit a running server over
  #                                       HTTP instead of running in-process
```

**Report shape** (`report.json`):

```json
{
  "dataset_name": "...",
  "langfuse_configured": true,
  "dataset_uploaded": true,
  "summary": {
    "total_cases": 40,
    "key_point_coverage_rate": 0.83,
    "red_line_violation_rate": 0.02,
    "hallucination_rate": 0.0,
    "mcp_tool_error_rate": 0.0,
    "end_to_end_latency": {"avg_seconds": 2.1, "p95_seconds": 4.7}
  },
  "results": [ /* one entry per test case, with the raw answer, judge verdict, latency, tool calls */ ]
}
```

Interpretation:
- `key_point_coverage_rate` — mean judge-assessed coverage of the mandatory
  key points across all cases. Below 0.70 means the agent is regularly
  missing required facts.
- `red_line_violation_rate` — fraction of cases with at least one red-line
  violation. Above 0.05 means the agent is regularly crossing a compliance
  boundary — treat any non-zero rate as worth investigating.
- `hallucination_rate` — fraction of cases where the judge specifically
  flagged the `fabrication` red line (a subset of the above).
- `mcp_tool_error_rate` — fraction of cases where a tool call returned an
  `{"error": ...}` payload. Only meaningful in in-process mode (the default);
  `--base-url` mode can't observe tool calls, so this is always 0 there.
- `end_to_end_latency` — wall-clock time per case from request to final
  answer, average and p95.

**With Langfuse configured**, the run also creates a Langfuse Dataset (named
via `--dataset`) with one item per generated query, and executes the batch as
a Langfuse Experiment (`client.run_experiment`) so every case is traced and
scored in the Langfuse UI under that dataset's runs. **Without Langfuse keys
set**, the same generation → run → judge → aggregate pipeline still executes
locally; `report.json` is produced identically, just with
`langfuse_configured: false` and `dataset_uploaded: false`, and no data is
sent to Langfuse.

**CI integration:** see `.github/workflows/langfuse-regression.yml` — it runs
this CLI on every push/PR to `main`, uploads `report.json` as a build
artifact, and fails the job if `red_line_violation_rate > 0.05` or
`key_point_coverage_rate < 0.70`. Set `ARK_API_KEY` / `ARK_CHAT_MODEL` /
`ARK_EMBEDDING_MODEL` and the `LANGFUSE_*` keys as repo secrets for it to run
against the real Ark API and upload to Langfuse; without `ARK_API_KEY` the
agent calls will fail per-case and the gate will (correctly) fail, signalling
missing CI configuration rather than a real regression.

## 5. Troubleshooting

**MCP span missing in a trace.** Every agent tool call is supposed to be
wrapped by `langfuse_tracing.trace_tool_call(tool_name, arguments)` in
`backend/main.py`'s `/api/agent_query` handler (search for
`with langfuse_tracing.trace_tool_call(...)`). If a tool call shows up in the
trace's `tool_calls` list but there's no matching span in Langfuse, check
that the call site is still wrapped — a refactor that pulls `_execute_agent_tool`
outside that `with` block is the usual cause.

**Tracing data not uploaded.** Confirm `LANGFUSE_PUBLIC_KEY` and
`LANGFUSE_SECRET_KEY` are set in the process's environment (`get_langfuse_client()`
logs `"Langfuse tracing disabled: ..."` at WARNING level if not, so check
logs first). If keys are set but nothing appears, the SDK batches events —
call `langfuse_tracing.flush_langfuse()` before the process exits (already
wired into `main.py`'s FastAPI shutdown event, and into
`langfuse_offline_eval.run_offline_evaluation` after the batch run). Short-
lived scripts that exit immediately after tracing calls are the most common
cause of "traces never showed up."

**Judge LLM timeout.** `langfuse_judge` enforces a hard timeout
(`LANGFUSE_JUDGE_TIMEOUT_SECONDS`, default 30s) on the judge LLM call and
returns a `"timeout"` status rather than hanging. If judge calls are timing
out frequently, raise `LANGFUSE_JUDGE_TIMEOUT_SECONDS`, and check whether the
judge is being pointed at a slower/larger model than the agent itself (it
reuses `ARK_CHAT_MODEL` via `shared.openai_client.get_chat_client()`).

**Dataset experiment fails without keys.** This is expected, not a bug:
`langfuse_offline_eval.run_offline_evaluation` checks
`langfuse_tracing.get_langfuse_client()` up front, and if it's `None` (no
keys, or the Langfuse API is unreachable), it skips `create_dataset` /
`run_experiment` entirely and falls back to a plain local loop over the same
generated test cases — `report.json` is still produced, just with
`langfuse_configured: false`. If you expected Langfuse upload and got the
local fallback instead, re-check the keys and look for a
`"Failed to create Langfuse dataset"` exception in the logs (network/auth
errors during `create_dataset` also fall back gracefully, logging the
underlying exception).
