"""
Offline batch evaluation for the LayaKB agent via Langfuse Datasets & Experiments.

Auto-generates 30-50 test queries from the business content available under
backend/data/ — any PDF/TXT/MD/DOCX policy documents found there, plus the
structured business data in users.json (products, excess amounts, covered
destinations, claim statuses) — and folds in the curated
evaluation/test_cases.py suite. Each query runs through the agent pipeline
(in-process by default, or over HTTP with --base-url) and is judged with the
same two-dimension rubric as langfuse_judge (key-point coverage + red-line
violations). Results are aggregated into a regression report:

    key_point_coverage_rate, red_line_violation_rate, hallucination_rate,
    mcp_tool_error_rate, end_to_end_latency (avg/p95)

If LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set, the whole run
degrades gracefully to a local evaluation: no Dataset/Experiment is created
in Langfuse, but the same report is produced from local execution.

CLI:
    python -m backend.langfuse_offline_eval --dataset <name> --output report.json
"""
import argparse
import glob
import json
import logging
import os
import sys
import time
from typing import Callable, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import langfuse_judge
import langfuse_tracing
from shared import openai_client, user_client

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MIN_QUERIES = 30
MAX_QUERIES = 50
DEFAULT_QUERY_COUNT = 40

_ALL_RED_LINE_IDS = [rl["id"] for rl in langfuse_judge.RED_LINES]


# ---------------------------------------------------------------------------
# Business document parsing (PDF / TXT / MD / DOCX)
# ---------------------------------------------------------------------------

def _read_pdf(path: str) -> str:
    import PyPDF2
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path: str) -> str:
    import docx
    document = docx.Document(path)
    return "\n".join(p.text for p in document.paragraphs)


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


_READERS: dict[str, Callable[[str], str]] = {
    ".pdf": _read_pdf,
    ".docx": _read_docx,
    ".txt": _read_text,
    ".md": _read_text,
}


def load_business_documents(docs_dir: str = DATA_DIR) -> list[dict]:
    """
    Parse every PDF/TXT/MD/DOCX file in `docs_dir` into {"file": name, "text": str}.
    Unsupported or unparseable files (including users.json, which is consumed
    separately by `_queries_from_user_data`) are skipped rather than raised,
    so a missing optional parser (e.g. python-docx) never breaks the run.
    """
    docs = []
    for path in sorted(glob.glob(os.path.join(docs_dir, "*"))):
        ext = os.path.splitext(path)[1].lower()
        reader = _READERS.get(ext)
        if reader is None:
            continue
        try:
            text = reader(path)
        except Exception:
            logger.warning("Skipping unparseable business document %s", path, exc_info=True)
            continue
        if text.strip():
            docs.append({"file": os.path.basename(path), "text": text})
    return docs


def _chunk(text: str, size: int = 900, overlap: int = 100) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap
    return chunks


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------

def _queries_from_documents(docs: list[dict], limit: int) -> list[dict]:
    """One templated query per document chunk; key point = the chunk's lead fragment."""
    queries = []
    for doc in docs:
        for chunk in _chunk(doc["text"]):
            if len(queries) >= limit:
                return queries
            lead = " ".join(chunk.split()[:20])
            if not lead:
                continue
            queries.append({
                "id": f"DOC-{len(queries) + 1:03d}",
                "question": f"Based on {doc['file']}, can you explain: {lead}...?",
                "user_id": None,
                "key_points": [lead],
                "red_lines": _ALL_RED_LINE_IDS,
                "source": f"document:{doc['file']}",
            })
    return queries


def _queries_from_user_data(limit: int) -> list[dict]:
    """
    Template personalised queries from the structured business data in
    users.json — the always-present business data source in backend/data/.
    """
    queries = []
    seen_products = set()
    for summary in user_client.list_users():
        uid = summary["id"]

        for policy in user_client.get_user_policies(uid) or []:
            if len(queries) >= limit:
                return queries
            key = (policy["product"], policy["version"])
            if key in seen_products:
                continue
            seen_products.add(key)
            queries.append({
                "id": f"USR-{len(queries) + 1:03d}",
                "question": (
                    f"What is my excess and which destinations are covered under my "
                    f"{policy['product']} policy ({policy['version']})?"
                ),
                "user_id": uid,
                "key_points": [
                    f"excess amount {policy['excess']}",
                    f"covered destinations {', '.join(policy['covered_destinations'])}",
                    policy["version"],
                ],
                "red_lines": _ALL_RED_LINE_IDS,
                "source": "users.json",
            })

        for claim in user_client.get_user_claims(uid) or []:
            if len(queries) >= limit:
                return queries
            queries.append({
                "id": f"CLM-{len(queries) + 1:03d}",
                "question": f"What is the status of claim {claim['claim_id']}?",
                "user_id": uid,
                "key_points": [claim["status"], claim["type"]],
                "red_lines": _ALL_RED_LINE_IDS,
                "source": "users.json",
            })
    return queries


def generate_test_queries(target_count: int = DEFAULT_QUERY_COUNT) -> list[dict]:
    """
    Auto-generate `target_count` (clamped to [30, 50]) test queries by combining:
      1. The curated evaluation/test_cases.py suite (already-authored key points).
      2. Any business documents parsed from backend/data/ (PDF/TXT/MD/DOCX).
      3. Template queries derived from the structured business data in users.json.
    """
    target_count = max(MIN_QUERIES, min(MAX_QUERIES, target_count))
    queries: list[dict] = []

    from evaluation.test_cases import TEST_CASES
    for tc in TEST_CASES:
        if len(queries) >= target_count:
            break
        queries.append({
            "id": tc["id"],
            "question": tc["question"],
            "user_id": tc.get("user_id"),
            "key_points": tc.get("expected_topics", []),
            "red_lines": _ALL_RED_LINE_IDS,
            "source": "evaluation.test_cases",
        })

    if len(queries) < target_count:
        docs = load_business_documents()
        queries.extend(_queries_from_documents(docs, target_count - len(queries)))

    if len(queries) < target_count:
        queries.extend(_queries_from_user_data(target_count - len(queries)))

    return queries[:target_count]


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------

def _run_agent_in_process(question: str, user_id: Optional[str]) -> dict:
    """
    Run one question through the same tool-calling loop as POST /api/agent_query,
    in-process (no HTTP round trip). Returns the answer plus enough detail
    (tool_calls, tool_error) to compute mcp_tool_error_rate.
    """
    import main as main_module  # backend/main.py

    user_context = user_client.build_user_context(user_id) if user_id else ""
    user_message = f"Customer context:\n{user_context}\n\nQuestion: {question}" if user_context else question

    messages = [
        {"role": "system", "content": main_module._agent_system_prompt()},
        {"role": "user", "content": user_message},
    ]

    tool_calls: list[str] = []
    tool_error = False
    for _ in range(6):
        choice = openai_client.chat_with_tools(messages, main_module._AGENT_TOOLS)
        if choice.finish_reason == "tool_calls":
            messages.append(choice.message.model_dump())
            for tc in choice.message.tool_calls:
                tool_calls.append(tc.function.name)
                result = main_module._execute_agent_tool(tc)
                if isinstance(result, dict) and "error" in result:
                    tool_error = True
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })
        else:
            return {"answer": choice.message.content or "", "tool_calls": tool_calls, "tool_error": tool_error}

    return {"answer": "", "tool_calls": tool_calls, "tool_error": True, "error": "did not converge"}


def _run_agent_http(base_url: str, question: str, user_id: Optional[str]) -> dict:
    """
    Run one question over HTTP against a live /api/agent_query deployment.
    Note: the HTTP response doesn't expose which tools were called, so
    tool_error is always False for this path (mcp_tool_error_rate is only
    meaningful in in-process mode).
    """
    import requests
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/agent_query",
        json={"question": question, "user_id": user_id},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return {"answer": data.get("answer", ""), "tool_calls": [], "tool_error": False}


# ---------------------------------------------------------------------------
# Per-case evaluation (agent run + judge)
# ---------------------------------------------------------------------------

def _evaluate_case(case: dict, agent_runner: Callable[[str, Optional[str]], dict], langfuse_client) -> dict:
    """
    Run one test case end-to-end: call the agent, time it, judge the answer
    with the same rubric as langfuse_judge.judge_trace, and (if Langfuse is
    configured and a trace is active) record the judge's scores on the trace.
    """
    start = time.perf_counter()
    error = None
    try:
        agent_result = agent_runner(case["question"], case.get("user_id"))
    except Exception as exc:
        logger.exception("Agent run failed for case %s", case["id"])
        agent_result = {"answer": "", "tool_calls": [], "tool_error": True}
        error = str(exc)
    latency = time.perf_counter() - start

    trace_id = ""
    if langfuse_client is not None:
        try:
            trace_id = langfuse_client.get_current_trace_id() or ""
        except Exception:
            trace_id = ""

    judge_result = langfuse_judge.judge_trace(
        trace_id=trace_id,
        question=case["question"],
        answer=agent_result.get("answer", ""),
        key_points=case.get("key_points", []),
        tool_calls=agent_result.get("tool_calls", []),
    )

    return {
        "id": case["id"],
        "question": case["question"],
        "user_id": case.get("user_id"),
        "source": case.get("source"),
        "answer": agent_result.get("answer", ""),
        "latency_seconds": latency,
        "tool_calls": agent_result.get("tool_calls", []),
        "tool_error": bool(agent_result.get("tool_error")),
        "agent_error": error,
        "judge_status": judge_result.get("status"),
        "coverage_rate": judge_result.get("coverage_rate"),
        "red_line_violations": judge_result.get("red_line_violations", []),
        "judge_pass": judge_result.get("pass"),
        "judge_comment": judge_result.get("comment"),
    }


# ---------------------------------------------------------------------------
# Langfuse dataset creation
# ---------------------------------------------------------------------------

def create_langfuse_dataset(client, dataset_name: str, cases: list[dict]) -> bool:
    """Create the Dataset and its items in Langfuse. Returns False (and logs) on any failure."""
    try:
        client.create_dataset(
            name=dataset_name,
            description="Auto-generated offline regression queries for the LayaKB agent.",
            metadata={"generator": "backend.langfuse_offline_eval", "case_count": len(cases)},
        )
        for case in cases:
            client.create_dataset_item(
                dataset_name=dataset_name,
                id=case["id"],
                input={"question": case["question"], "user_id": case.get("user_id")},
                metadata={
                    "key_points": case["key_points"],
                    "red_lines": case["red_lines"],
                    "source": case.get("source"),
                },
            )
        return True
    except Exception:
        logger.exception("Failed to create Langfuse dataset '%s'", dataset_name)
        return False


# ---------------------------------------------------------------------------
# Report aggregation
# ---------------------------------------------------------------------------

def _p95(sorted_values: list[float]) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(round(0.95 * (len(sorted_values) - 1))))
    return sorted_values[idx]


def build_report(dataset_name: str, results: list[dict], langfuse_configured: bool, dataset_uploaded: bool) -> dict:
    total = len(results)
    coverage_rates = [r["coverage_rate"] for r in results if r["coverage_rate"] is not None]
    red_line_flags = [1 if r["red_line_violations"] else 0 for r in results]
    hallucination_flags = [
        1 if any(v.get("id") == "fabrication" for v in r["red_line_violations"]) else 0
        for r in results
    ]
    tool_error_flags = [1 if r["tool_error"] else 0 for r in results]
    latencies = sorted(r["latency_seconds"] for r in results)

    summary = {
        "total_cases": total,
        "key_point_coverage_rate": round(sum(coverage_rates) / len(coverage_rates), 4) if coverage_rates else 0.0,
        "red_line_violation_rate": round(sum(red_line_flags) / total, 4) if total else 0.0,
        "hallucination_rate": round(sum(hallucination_flags) / total, 4) if total else 0.0,
        "mcp_tool_error_rate": round(sum(tool_error_flags) / total, 4) if total else 0.0,
        "end_to_end_latency": {
            "avg_seconds": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "p95_seconds": round(_p95(latencies), 3),
        },
    }

    return {
        "dataset_name": dataset_name,
        "langfuse_configured": langfuse_configured,
        "dataset_uploaded": dataset_uploaded,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_offline_evaluation(
    dataset_name: str,
    target_count: int = DEFAULT_QUERY_COUNT,
    base_url: Optional[str] = None,
) -> dict:
    """
    Generate test queries, optionally upload them as a Langfuse Dataset, run
    every query through the agent + judge (via a Langfuse Experiment when
    configured, otherwise a plain local loop), and return the aggregate
    report dict (the same shape written to --output).
    """
    cases = generate_test_queries(target_count)
    logger.info("Generated %d test queries for offline evaluation", len(cases))

    agent_runner: Callable[[str, Optional[str]], dict] = (
        (lambda q, uid: _run_agent_http(base_url, q, uid)) if base_url
        else _run_agent_in_process
    )

    client = langfuse_tracing.get_langfuse_client()
    dataset_uploaded = False
    if client is not None:
        dataset_uploaded = create_langfuse_dataset(client, dataset_name, cases)
    else:
        logger.warning(
            "Langfuse keys not configured — running offline evaluation locally, "
            "no Dataset/Experiment will be created."
        )

    if client is not None:
        def _task(*, item, **kwargs):
            return _evaluate_case(item["metadata"]["_case"], agent_runner, client)

        def _coverage_eval(*, output, **kwargs):
            return {"name": "key_point_coverage_rate", "value": output.get("coverage_rate") or 0.0}

        def _red_line_eval(*, output, **kwargs):
            return {"name": "red_line_violation", "value": bool(output.get("red_line_violations"))}

        experiment = client.run_experiment(
            name=f"offline_eval:{dataset_name}",
            data=[
                {"input": {"question": c["question"], "user_id": c.get("user_id")}, "metadata": {"_case": c}}
                for c in cases
            ],
            task=_task,
            evaluators=[_coverage_eval, _red_line_eval],
            max_concurrency=3,
        )
        results = [r.output for r in experiment.item_results]
        langfuse_tracing.flush_langfuse()
    else:
        results = [_evaluate_case(case, agent_runner, None) for case in cases]

    return build_report(dataset_name, results, client is not None, dataset_uploaded)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="LayaKB offline batch evaluation via Langfuse Datasets & Experiments."
    )
    parser.add_argument("--dataset", default=f"offline-eval-{int(time.time())}",
                         help="Langfuse dataset name (also recorded in the local report).")
    parser.add_argument("--output", default="report.json",
                         help="Path to write the aggregate JSON report.")
    parser.add_argument("--target-count", type=int, default=DEFAULT_QUERY_COUNT,
                         help="Number of auto-generated test queries (clamped to 30-50).")
    parser.add_argument("--base-url", default=None,
                         help="Call the agent over HTTP at this base URL instead of running it in-process.")
    parser.add_argument("--red-line-threshold", type=float, default=0.05)
    parser.add_argument("--coverage-threshold", type=float, default=0.70)
    parser.add_argument("--fail-on-threshold", action="store_true",
                         help="Exit non-zero if the report violates the red-line/coverage thresholds.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    report = run_offline_evaluation(args.dataset, args.target_count, args.base_url)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(json.dumps(report["summary"], indent=2))
    print(f"\nReport written to {args.output}")

    if args.fail_on_threshold:
        summary = report["summary"]
        if summary["red_line_violation_rate"] > args.red_line_threshold:
            print(f"FAIL: red_line_violation_rate {summary['red_line_violation_rate']} > {args.red_line_threshold}")
            return 1
        if summary["key_point_coverage_rate"] < args.coverage_threshold:
            print(f"FAIL: key_point_coverage_rate {summary['key_point_coverage_rate']} < {args.coverage_threshold}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
