"""
Langfuse tracing for the LayaKB agent pipeline.

This module wraps the Langfuse Python SDK (v4, OpenTelemetry-based) to give the
FastAPI agent pipeline observability without leaking Langfuse specifics into
business logic. Every public helper degrades to a no-op if Langfuse is not
configured (missing keys) or unreachable, so tracing can never break a request.

Traced agent events (see the *_EVENT names below):
    user_input, system_prompt, llm_call, mcp_tool_invocation,
    azure_function_api_request, kb_retrieval, tool_call_execution,
    agent_loop_iteration, final_response, exception, latency, token_usage
"""
import functools
import inspect
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

from langfuse import Langfuse, get_client, propagate_attributes

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event type constants — the fixed vocabulary of agent-pipeline events.
# ---------------------------------------------------------------------------
EVENT_USER_INPUT = "user_input"
EVENT_SYSTEM_PROMPT = "system_prompt"
EVENT_LLM_CALL = "llm_call"
EVENT_MCP_TOOL_INVOCATION = "mcp_tool_invocation"
EVENT_AZURE_FUNCTION_API_REQUEST = "azure_function_api_request"
EVENT_KB_RETRIEVAL = "kb_retrieval"
EVENT_TOOL_CALL_EXECUTION = "tool_call_execution"
EVENT_AGENT_LOOP_ITERATION = "agent_loop_iteration"
EVENT_FINAL_RESPONSE = "final_response"
EVENT_EXCEPTION = "exception"
EVENT_LATENCY = "latency"
EVENT_TOKEN_USAGE = "token_usage"

# Tool names that should be traced as `mcp_tool_invocation` rather than a
# generic `tool_call_execution` — these mirror backend/mcp_server.py.
_MCP_TOOL_NAMES = {
    "get_user_profile",
    "get_user_context_summary",
    "search_users",
    "list_all_users",
    "get_user_claims",
    "get_user_policies",
}

_lock = threading.Lock()
_client: Optional[Langfuse] = None
_client_init_attempted = False


def get_langfuse_client() -> Optional[Langfuse]:
    """
    Singleton accessor for the Langfuse client.

    Returns None (rather than raising) when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
    are not configured, so callers can treat tracing as best-effort.
    """
    global _client, _client_init_attempted
    if _client is not None:
        return _client
    with _lock:
        if _client is not None or _client_init_attempted:
            return _client
        _client_init_attempted = True
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        if not public_key or not secret_key:
            logger.warning(
                "Langfuse tracing disabled: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set."
            )
            return None
        try:
            _client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                environment=os.environ.get("LANGFUSE_ENVIRONMENT", "dev"),
            )
        except Exception:
            logger.exception("Failed to initialize Langfuse client")
            _client = None
        return _client


def flush_langfuse() -> None:
    """Force-upload any buffered traces. Call on shutdown / after batch jobs."""
    client = get_langfuse_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.exception("Failed to flush Langfuse client")


# ---------------------------------------------------------------------------
# Request metadata extraction
# ---------------------------------------------------------------------------

# Maps HTTP header name -> metadata key stored on the trace.
_METADATA_HEADERS = {
    "x-function-instance-id": "function_instance_id",
    "x-tenant-id": "tenant_id",
    "x-spn-client-id": "spn_client_id",
    "x-mcp-endpoint": "mcp_endpoint",
    "x-user-session-id": "user_session_id",
}


def extract_trace_metadata(headers: Any) -> dict:
    """
    Build a metadata dict from FastAPI/Starlette request headers.

    `headers` is expected to be a case-insensitive mapping (e.g. `Request.headers`)
    but a plain dict also works since lookups are lower-cased before matching.
    """
    metadata = {}
    lowered = {str(k).lower(): v for k, v in dict(headers or {}).items()}
    for header_name, meta_key in _METADATA_HEADERS.items():
        if header_name in lowered:
            metadata[meta_key] = lowered[header_name]
    return metadata


# ---------------------------------------------------------------------------
# Generic span decorator
# ---------------------------------------------------------------------------

def _safe_repr(value: Any, limit: int = 4000) -> Any:
    """Best-effort JSON-serialisable trimming so large payloads don't blow up traces."""
    try:
        if isinstance(value, (str, int, float, bool)) or value is None:
            s = value if not isinstance(value, str) else value
            if isinstance(s, str) and len(s) > limit:
                return s[:limit] + "...<truncated>"
            return s
        if isinstance(value, (list, tuple)):
            return [_safe_repr(v, limit) for v in value[:20]]
        if isinstance(value, dict):
            return {k: _safe_repr(v, limit) for k, v in list(value.items())[:50]}
        return _safe_repr(repr(value), limit)
    except Exception:
        return "<unrepresentable>"


def trace_span(
    name: Optional[str] = None,
    as_type: str = "span",
    event_type: Optional[str] = None,
    capture_args: bool = True,
    capture_result: bool = True,
):
    """
    Decorator that wraps a function call in a Langfuse observation.

    Works for both sync and async callables. If a `name` is not given the
    function's __name__ is used. `event_type` (one of the EVENT_* constants)
    is stored as `metadata.event_type` so events can be filtered in Langfuse.
    No-ops transparently when Langfuse is not configured.
    """

    def decorator(fn: Callable) -> Callable:
        span_name = name or fn.__name__

        def _build_input(args, kwargs):
            if not capture_args:
                return None
            try:
                bound = inspect.signature(fn).bind_partial(*args, **kwargs)
                bound.apply_defaults()
                arguments = dict(bound.arguments)
                arguments.pop("self", None)
                return _safe_repr(arguments)
            except Exception:
                return _safe_repr({"args": args, "kwargs": kwargs})

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                client = get_langfuse_client()
                if client is None:
                    return await fn(*args, **kwargs)
                start = time.perf_counter()
                with client.start_as_current_observation(
                    name=span_name,
                    as_type=as_type,
                    input=_build_input(args, kwargs),
                    metadata={"event_type": event_type} if event_type else None,
                ) as span:
                    try:
                        result = await fn(*args, **kwargs)
                        if capture_result:
                            span.update(output=_safe_repr(result))
                        span.update(metadata={"latency_seconds": time.perf_counter() - start})
                        return result
                    except Exception as exc:
                        span.update(level="ERROR", status_message=str(exc))
                        raise

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            client = get_langfuse_client()
            if client is None:
                return fn(*args, **kwargs)
            start = time.perf_counter()
            with client.start_as_current_observation(
                name=span_name,
                as_type=as_type,
                input=_build_input(args, kwargs),
                metadata={"event_type": event_type} if event_type else None,
            ) as span:
                try:
                    result = fn(*args, **kwargs)
                    if capture_result:
                        span.update(output=_safe_repr(result))
                    span.update(metadata={"latency_seconds": time.perf_counter() - start})
                    return result
                except Exception as exc:
                    span.update(level="ERROR", status_message=str(exc))
                    raise

        return sync_wrapper

    return decorator


# ---------------------------------------------------------------------------
# Lightweight event logging (no dedicated span needed)
# ---------------------------------------------------------------------------

def log_event(event_type: str, payload: Optional[dict] = None, level: str = "DEFAULT") -> None:
    """
    Record a point-in-time event on the current trace (e.g. user_input,
    system_prompt, token_usage) without opening a new span.
    """
    client = get_langfuse_client()
    if client is None:
        return
    try:
        client.create_event(
            name=event_type,
            input=_safe_repr(payload) if payload else None,
            metadata={"event_type": event_type},
            level=level,
        )
    except Exception:
        logger.exception("Failed to log Langfuse event %s", event_type)


def log_exception(exc: Exception, context: Optional[dict] = None) -> None:
    """Record an `exception` event with the error message and optional context."""
    log_event(
        EVENT_EXCEPTION,
        payload={"error": str(exc), "type": type(exc).__name__, **(context or {})},
        level="ERROR",
    )


def log_token_usage(model: str, usage: dict) -> None:
    """Record a `token_usage` event. `usage` is typically an OpenAI-style usage dict."""
    log_event(EVENT_TOKEN_USAGE, payload={"model": model, "usage": usage})


# ---------------------------------------------------------------------------
# Tool call tracing — used by _execute_agent_tool in main.py
# ---------------------------------------------------------------------------

@contextmanager
def trace_tool_call(tool_name: str, arguments: dict):
    """
    Context manager that traces a single agent tool invocation.

    Classifies the span as `mcp_tool_invocation` for tools that mirror the MCP
    user-data server, and `tool_call_execution` for everything else (e.g.
    search_knowledge_base -> kb_retrieval, generate_sas_url -> azure_function_api_request).
    """
    if tool_name == "search_knowledge_base":
        event_type = EVENT_KB_RETRIEVAL
    elif tool_name == "generate_sas_url":
        event_type = EVENT_AZURE_FUNCTION_API_REQUEST
    elif tool_name in _MCP_TOOL_NAMES:
        event_type = EVENT_MCP_TOOL_INVOCATION
    else:
        event_type = EVENT_TOOL_CALL_EXECUTION

    client = get_langfuse_client()
    if client is None:
        yield None
        return

    with client.start_as_current_observation(
        name=f"tool:{tool_name}",
        as_type="tool",
        input=_safe_repr(arguments),
        metadata={"event_type": event_type, "tool_name": tool_name},
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.update(level="ERROR", status_message=str(exc))
            raise


@contextmanager
def trace_agent_loop_iteration(iteration: int, message_count: int):
    """Context manager tracing one turn of the agent's tool-calling loop."""
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    with client.start_as_current_observation(
        name=f"agent_loop_iteration:{iteration}",
        as_type="span",
        input={"iteration": iteration, "message_count": message_count},
        metadata={"event_type": EVENT_AGENT_LOOP_ITERATION},
    ) as span:
        yield span


@contextmanager
def trace_llm_call(model: str, message_count: int):
    """Context manager tracing a single call to the chat-completions endpoint."""
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    with client.start_as_current_observation(
        name="llm_call",
        as_type="generation",
        input={"message_count": message_count},
        model=model,
        metadata={"event_type": EVENT_LLM_CALL},
    ) as span:
        yield span


# ---------------------------------------------------------------------------
# High-level convenience wrappers mirroring the FastAPI endpoints
# ---------------------------------------------------------------------------

@contextmanager
def observe_query(question: str, user_id: Optional[str] = None, request_metadata: Optional[dict] = None):
    """
    Root trace for POST /api/query (plain RAG endpoint).

    Usage:
        with observe_query(question, user_id, extract_trace_metadata(request.headers)) as span:
            ... run pipeline ...
            if span: span.update(output=answer)
    """
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    metadata = dict(request_metadata or {})
    with propagate_attributes(
        user_id=user_id,
        metadata=metadata,
        tags=["api_query", "rag"],
    ):
        with client.start_as_current_observation(
            name="api_query",
            as_type="span",
            input={"question": question, "user_id": user_id},
            metadata={"event_type": EVENT_USER_INPUT, **metadata},
        ) as span:
            try:
                yield span
            except Exception as exc:
                span.update(level="ERROR", status_message=str(exc))
                log_exception(exc, {"endpoint": "/api/query"})
                raise


@contextmanager
def observe_agent_query(question: str, user_id: Optional[str] = None, request_metadata: Optional[dict] = None):
    """
    Root trace for POST /api/agent_query (tool-calling agent endpoint).

    Wraps the whole multi-turn agent loop as a single Langfuse trace; the
    per-iteration and per-tool-call spans created via `trace_agent_loop_iteration`
    / `trace_tool_call` nest underneath it automatically.
    """
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    metadata = dict(request_metadata or {})
    with propagate_attributes(
        user_id=user_id,
        metadata=metadata,
        tags=["api_agent_query", "agent"],
    ):
        with client.start_as_current_observation(
            name="api_agent_query",
            as_type="agent",
            input={"question": question, "user_id": user_id},
            metadata={"event_type": EVENT_USER_INPUT, **metadata},
        ) as span:
            try:
                yield span
            except Exception as exc:
                span.update(level="ERROR", status_message=str(exc))
                log_exception(exc, {"endpoint": "/api/agent_query"})
                raise
