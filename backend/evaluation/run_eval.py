"""
CLI runner for the Laya Healthcare agent evaluation.

Usage:
    python evaluation/run_eval.py                     # run all test cases
    python evaluation/run_eval.py --category kb_retrieval
    python evaluation/run_eval.py --ids TC01 TC05 TC09
    python evaluation/run_eval.py --out results.json  # save raw results
"""
import argparse
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from evaluation.test_cases import TEST_CASES
from evaluation.evaluator import evaluate_case
from shared import openai_client, search_client, user_client


def _agent_fn(question: str, user_id: str | None) -> dict:
    """Thin wrapper that calls the KB query pipeline directly (no HTTP)."""
    import json as _json
    from shared import blob_client

    # Build tool executor inline (mirrors main.py logic)
    def _search_kb(query, doc_type="", product_name=""):
        vec = openai_client.get_embedding(query)
        parts = []
        if doc_type:  parts.append(f"doc_type eq '{doc_type}'")
        if product_name: parts.append(f"product_name eq '{product_name}'")
        f = " and ".join(parts) or None
        return search_client.hybrid_search(query, vec, top_k=5, filter_expr=f)

    def _execute_tool(tc):
        name = tc.function.name
        args = _json.loads(tc.function.arguments or "{}")
        if name == "search_knowledge_base":
            hits = _search_kb(args.get("query",""), args.get("doc_type",""), args.get("product_name",""))
            return {"results": hits}
        if name == "get_user_profile":
            u = user_client.get_user_by_id(args.get("user_id",""))
            return u or {"error": "not found"}
        if name == "get_user_policies":
            p = user_client.get_user_policies(args.get("user_id",""))
            return {"policies": p} if p is not None else {"error": "not found"}
        if name == "get_user_claims":
            c = user_client.get_user_claims(args.get("user_id",""))
            return {"claims": c} if c is not None else {"error": "not found"}
        if name == "search_users":
            return {"users": user_client.search_users(args.get("query",""))}
        return {"error": f"unknown tool: {name}"}

    # Import prompts and tools from main
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import importlib
    main = importlib.import_module("main")

    user_context = user_client.build_user_context(user_id) if user_id else ""
    content = f"Customer context:\n{user_context}\n\nQuestion: {question}" if user_context else question

    messages = [
        {"role": "system", "content": main._AGENT_SYSTEM_PROMPT},
        {"role": "user",   "content": content},
    ]

    for _ in range(6):
        choice = openai_client.chat_with_tools(messages, main._AGENT_TOOLS)
        if choice.finish_reason == "tool_calls":
            messages.append(choice.message.model_dump())
            for tc in choice.message.tool_calls:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _json.dumps(_execute_tool(tc)),
                })
        else:
            return {"answer": choice.message.content or "", "sources": []}

    return {"answer": "Agent did not converge.", "sources": []}


def _print_result(r: dict):
    status = "✓" if r["hard_pass"] else "✗"
    scores = r["scores"]
    parts = [
        f"R={scores.get('relevance',0):.2f}",
        f"F={scores.get('faithfulness',0):.2f}",
        f"C={scores.get('completeness',0):.2f}",
    ]
    if scores.get("personalisation") is not None:
        parts.append(f"P={scores['personalisation']:.2f}")
    print(f"  {status} [{r['id']}] {r['category']:<18} overall={r['overall']:.2f}  "
          + "  ".join(parts))
    if r["hard_failures"]:
        for hf in r["hard_failures"]:
            print(f"       ⚠  {hf}")
    print(f"       ↳ {scores.get('reasoning','')}")


def _print_summary(results: list[dict]):
    total = len(results)
    hard_ok = sum(1 for r in results if r["hard_pass"])
    overall_avg = sum(r["overall"] for r in results) / total if total else 0

    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r["overall"])

    print("\n" + "="*60)
    print(f"  EVALUATION SUMMARY  ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print("="*60)
    print(f"  Cases run    : {total}")
    print(f"  Hard checks  : {hard_ok}/{total} passed")
    print(f"  Overall avg  : {overall_avg:.3f}")
    print()
    print("  By category:")
    for cat, scores in sorted(by_cat.items()):
        avg = sum(scores) / len(scores)
        print(f"    {cat:<22} avg={avg:.3f}  (n={len(scores)})")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Run Laya KB agent evaluation")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--ids", nargs="+", help="Run specific test case IDs")
    parser.add_argument("--out", help="Save results JSON to file")
    args = parser.parse_args()

    cases = TEST_CASES
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if args.ids:
        cases = [c for c in cases if c["id"] in args.ids]

    if not cases:
        print("No test cases matched the filter.")
        sys.exit(1)

    print(f"Running {len(cases)} test case(s)...\n")

    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} — {case['question'][:70]}...")
        result = evaluate_case(case, _agent_fn)
        _print_result(result)
        results.append(result)

    _print_summary(results)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {args.out}")


if __name__ == "__main__":
    main()
