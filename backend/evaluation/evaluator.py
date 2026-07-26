"""
LLM-as-judge evaluator for the Laya Healthcare KB agent.

Scores each agent response on four dimensions (0.0 – 1.0):
  - relevance:       Does the answer directly address the question?
  - faithfulness:    Is every claim grounded in the retrieved policy documents?
  - completeness:    Are all key topics from expected_topics covered?
  - personalisation: (only when user_id is set) Does the answer reflect the
                     customer's specific policy details?
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from shared import openai_client

JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for an insurance knowledge base assistant.
You assess agent responses against specific quality criteria.
Always return valid JSON only — no markdown, no extra text."""

def _judge(question: str, answer: str, expected_topics: list[str],
           user_context: str, policy_version: str | None) -> dict:
    """Call LLM judge and return scores dict."""
    personalisation_instruction = (
        """  "personalisation": a score from 0.0 to 1.0 for whether the answer specifically references
    the customer's own policy details (policy number, product name, excess amount, covered destinations,
    pre-existing conditions, or open claims) rather than giving a generic answer."""
        if user_context else
        """  "personalisation": null  // no user context provided, skip this dimension"""
    )

    prompt = f"""Evaluate the following agent response and return a JSON object with these fields:

Question: {question}

{"Customer context:\n" + user_context + "\n" if user_context else ""}
Agent answer:
{answer}

Expected topics the answer should cover: {expected_topics}
{"Expected policy version referenced: " + policy_version if policy_version else ""}

Scoring criteria (each 0.0 to 1.0):
  "relevance": does the answer directly and completely address the question?
  "faithfulness": are all claims in the answer grounded in insurance policy documents,
    with no hallucinated facts or invented figures?
  "completeness": what fraction of the expected_topics are clearly addressed?
{personalisation_instruction}
  "reasoning": a brief (1-2 sentence) explanation of the scores.

Return ONLY a valid JSON object like:
{{
  "relevance": 0.85,
  "faithfulness": 0.90,
  "completeness": 0.75,
  "personalisation": 0.80,
  "reasoning": "..."
}}"""

    raw = openai_client.chat_completion(JUDGE_SYSTEM_PROMPT, prompt)

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        scores = json.loads(raw)
    except json.JSONDecodeError:
        scores = {
            "relevance": 0.0, "faithfulness": 0.0,
            "completeness": 0.0, "personalisation": None,
            "reasoning": f"Judge returned unparseable output: {raw[:200]}",
        }
    return scores


def evaluate_case(test_case: dict, agent_fn) -> dict:
    """
    Run one test case through the agent and judge the response.

    agent_fn(question, user_id) -> {"answer": str, "sources": list}
    """
    from shared import user_client

    question = test_case["question"]
    user_id = test_case.get("user_id")
    user_context = user_client.build_user_context(user_id) if user_id else ""

    try:
        result = agent_fn(question, user_id)
        answer = result.get("answer", "")
        sources = result.get("sources", [])
        error = None
    except Exception as exc:
        answer = ""
        sources = []
        error = str(exc)

    # Hard checks
    hard_pass = True
    hard_failures = []
    for s in test_case.get("should_contain", []):
        if s.lower() not in answer.lower():
            hard_pass = False
            hard_failures.append(f"missing required: '{s}'")
    for s in test_case.get("should_not_contain", []):
        if s.lower() in answer.lower():
            hard_pass = False
            hard_failures.append(f"found forbidden: '{s}'")

    # LLM judge scores
    if answer:
        scores = _judge(
            question=question,
            answer=answer,
            expected_topics=test_case.get("expected_topics", []),
            user_context=user_context,
            policy_version=test_case.get("policy_version"),
        )
    else:
        scores = {
            "relevance": 0.0, "faithfulness": 0.0,
            "completeness": 0.0, "personalisation": None,
            "reasoning": f"Agent returned empty answer. Error: {error}",
        }

    # Overall score: mean of non-null numeric scores
    numeric = [v for v in [scores.get("relevance"), scores.get("faithfulness"),
                            scores.get("completeness")] if v is not None]
    if scores.get("personalisation") is not None:
        numeric.append(scores["personalisation"])
    overall = round(sum(numeric) / len(numeric), 3) if numeric else 0.0

    return {
        "id": test_case["id"],
        "category": test_case["category"],
        "question": question,
        "user_id": user_id,
        "answer": answer,
        "sources_count": len(sources),
        "hard_pass": hard_pass,
        "hard_failures": hard_failures,
        "scores": scores,
        "overall": overall,
        "error": error,
    }
