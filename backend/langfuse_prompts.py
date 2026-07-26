"""
Langfuse Prompt Management for the LayaKB agent.

Fetches SYSTEM_PROMPT and _AGENT_SYSTEM_PROMPT from Langfuse instead of
hardcoding them in main.py, with version control, environment labels
(dev / staging / prod), an in-memory TTL cache, and a hardcoded fallback so
the API keeps serving answers even if Langfuse is unreachable.

Prompt names used in Langfuse:
    "system_prompt"        — plain RAG endpoint (/api/query)
    "agent_system_prompt"  — tool-calling agent endpoint (/api/agent_query)
"""
import logging
import os
import sys
import threading
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langfuse.model import TextPromptClient

from langfuse_tracing import get_langfuse_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_NAME = "system_prompt"
AGENT_SYSTEM_PROMPT_NAME = "agent_system_prompt"

DEFAULT_ENVIRONMENT = os.environ.get("LANGFUSE_ENVIRONMENT", "dev")
_CACHE_TTL_SECONDS = int(os.environ.get("LANGFUSE_PROMPT_CACHE_TTL", "300"))

# ---------------------------------------------------------------------------
# Hardcoded fallback prompts — used verbatim if Langfuse is unreachable or the
# prompt hasn't been created there yet. These are the same texts that used to
# live directly in backend/main.py.
# ---------------------------------------------------------------------------

FALLBACK_PROMPTS = {
    SYSTEM_PROMPT_NAME: """You are a knowledgeable assistant for Laya Healthcare insurance products. \
You answer questions strictly based on the provided policy documents.

Knowledge base covers:
- Travel Insurance: Policy Wordings, Insurance Product Information Documents (Single & Annual Multi-Trip, Backpacker), Terms of Business
- Car Hire Excess Insurance: Policy Wordings, Insurance Product Information Documents (Annual Multi-Trip with CDW/SLI, Annual Multi-Trip, Single Trip), Terms of Business
- Two policy versions: documents for policies bound BEFORE November 2025 and AFTER November 2025

Response rules:
1. Answer only from the provided context. If the answer is not in the context, say: \
"I'm unable to find this information in the available Laya Healthcare policy documents. \
Please contact Laya Healthcare directly or refer to your policy document."
2. Always specify which policy version applies (pre- or post-November 2025) when relevant.
3. Use plain, clear English. Avoid jargon where possible; define technical terms when first used.
4. For coverage limits, exclusions, or claim procedures, quote the relevant clause or section directly.
5. End every response with a source citation in this format:
   Source: {document name} | {page or section reference}""",

    AGENT_SYSTEM_PROMPT_NAME: """You are a specialist insurance advisor for Laya Healthcare. \
You have access to a knowledge base containing the full text of all Laya Healthcare policy documents.

## Documents in the knowledge base

Travel Insurance (two versions: policies bound before / after November 2025):
- Laya Healthcare Travel Insurance Policy Document
- Laya Healthcare Medicare Travel Insurance Policy Document
- Single & Annual Multi-Trip Travel Insurance IPID
- Backpacker Travel Insurance IPID
- Terms of Business

Car Hire Excess Insurance (two versions: policies bound before / after November 2025):
- Laya Healthcare Car Hire Excess Insurance Policy Document
- Car Hire Excess Insurance Annual Multi-Trip with CDW and SLI IPID
- Car Hire Excess Insurance Annual Multi-Trip IPID
- Car Hire Excess Insurance Single Trip IPID
- Terms of Business

## Behaviour rules

1. If a customer context is provided in the message, use get_user_profile or get_user_policies \
to retrieve their exact coverage details before searching the knowledge base.
2. Always call search_knowledge_base to find the relevant policy clauses for the question.
3. Cross-reference the customer's specific policy (product, version, excess, destinations) \
with what the knowledge base says — tailor the answer to their actual coverage.
4. If the question concerns a specific document or the user wants to read the source, \
call generate_sas_url to produce a download link.
5. Clarify which policy version (pre- or post-November 2025) applies to this customer.
6. Be precise: quote exact coverage limits, excess amounts, exclusions, and clause numbers.
7. Never speculate beyond what the documents state. If information is absent, say so clearly.
8. Do not give personal financial or legal advice; direct the user to contact Laya Healthcare \
or a licensed broker for decisions specific to their situation.

## Required response format

Structure every answer as follows:

**Answer**
<direct response to the question, in plain English>

**Key details**
- <bullet point for each relevant coverage limit, exclusion, or condition>

**Policy version**
<state whether this applies to policies before or after November 2025, or both>

---
**Sources**
- Document: {source_file_name} | Page/Section: {page_number or section}
- Link: {sas_url} (valid for 24 hours)
""",
}

# ---------------------------------------------------------------------------
# In-memory TTL cache: (name, environment, version) -> (text, fetched_at)
# ---------------------------------------------------------------------------
_cache: dict[tuple[str, str, str], tuple[str, float]] = {}
_cache_lock = threading.Lock()


def _cache_key(name: str, environment: str, version: str) -> tuple[str, str, str]:
    return (name, environment, str(version))


def _get_cached(key: tuple[str, str, str]) -> Optional[str]:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        text, fetched_at = entry
        if time.time() - fetched_at > _CACHE_TTL_SECONDS:
            del _cache[key]
            return None
        return text


def _set_cached(key: tuple[str, str, str], text: str) -> None:
    with _cache_lock:
        _cache[key] = (text, time.time())


def _invalidate(name: str, environment: str) -> None:
    with _cache_lock:
        for key in [k for k in _cache if k[0] == name and k[1] == environment]:
            del _cache[key]


def clear_cache() -> None:
    """Drop all cached prompt text. Mostly useful for tests."""
    with _cache_lock:
        _cache.clear()


def _extract_text(prompt_obj) -> str:
    """Pull raw prompt text out of a Langfuse TextPromptClient/ChatPromptClient."""
    if isinstance(prompt_obj, TextPromptClient):
        return prompt_obj.prompt
    # Chat-type prompts: join message contents into one text blob.
    if hasattr(prompt_obj, "prompt") and isinstance(prompt_obj.prompt, list):
        return "\n".join(m.get("content", "") for m in prompt_obj.prompt if isinstance(m, dict))
    return str(prompt_obj)


def get_prompt(name: str, environment: str = DEFAULT_ENVIRONMENT, version: str = "latest") -> str:
    """
    Fetch a prompt's raw text from Langfuse Prompt Management.

    Args:
        name: Prompt name in Langfuse, e.g. "system_prompt" or "agent_system_prompt".
        environment: One of "dev" | "staging" | "prod". Mapped to a Langfuse label
            of the same name, so promoting a prompt = applying that label to a version.
        version: A specific version number (as int or numeric string), or "latest"
            to resolve via the environment label.

    Falls back to the hardcoded prompt text (FALLBACK_PROMPTS) if Langfuse is not
    configured, the prompt doesn't exist yet, or the API call fails for any reason.
    """
    key = _cache_key(name, environment, version)
    cached = _get_cached(key)
    if cached is not None:
        return cached

    fallback_text = FALLBACK_PROMPTS.get(name, "")
    client = get_langfuse_client()
    if client is None:
        return fallback_text

    try:
        if version != "latest":
            prompt_obj = client.get_prompt(
                name, version=int(version), fallback=fallback_text or None,
                cache_ttl_seconds=_CACHE_TTL_SECONDS,
            )
        else:
            prompt_obj = client.get_prompt(
                name, label=environment, fallback=fallback_text or None,
                cache_ttl_seconds=_CACHE_TTL_SECONDS,
            )
        text = _extract_text(prompt_obj)
    except Exception:
        logger.exception(
            "Failed to fetch prompt '%s' (environment=%s, version=%s) from Langfuse; using fallback",
            name, environment, version,
        )
        text = fallback_text

    _set_cached(key, text)
    return text


def rollback_prompt(name: str, target_version: int, environment: str = DEFAULT_ENVIRONMENT) -> bool:
    """
    One-click rollback: re-point the given environment's label at `target_version`.

    Langfuse prompts are immutable per version; "rollback" means moving the
    environment label (e.g. "prod") back onto an older version so that
    get_prompt(name, environment=..., version="latest") resolves to it again.
    Returns True on success, False if Langfuse is unreachable or the call fails.
    """
    client = get_langfuse_client()
    if client is None:
        logger.warning("Cannot rollback prompt '%s': Langfuse client not configured", name)
        return False
    try:
        client.update_prompt(name=name, version=target_version, new_labels=[environment])
        _invalidate(name, environment)
        logger.info("Rolled back prompt '%s' to version %s for environment '%s'",
                    name, target_version, environment)
        return True
    except Exception:
        logger.exception("Failed to rollback prompt '%s' to version %s", name, target_version)
        return False


def create_or_update_prompt(name: str, text: str, environment: str = DEFAULT_ENVIRONMENT) -> bool:
    """
    Push a new prompt version to Langfuse and label it for `environment`.
    Used by the prompt-migration step (see INTEGRATION.md) to seed Langfuse
    with the hardcoded prompts on first setup.
    """
    client = get_langfuse_client()
    if client is None:
        logger.warning("Cannot create prompt '%s': Langfuse client not configured", name)
        return False
    try:
        client.create_prompt(name=name, prompt=text, labels=[environment], type="text")
        _invalidate(name, environment)
        return True
    except Exception:
        logger.exception("Failed to create/update prompt '%s'", name)
        return False
