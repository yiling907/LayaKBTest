import json
import os
from functools import lru_cache

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")


@lru_cache(maxsize=1)
def _load() -> list[dict]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_user_by_id(user_id: str) -> dict | None:
    return next((u for u in _load() if u["id"] == user_id), None)


def search_users(query: str, limit: int = 10) -> list[dict]:
    q = query.lower()
    matches = [
        u for u in _load()
        if q in u["name"].lower()
        or q in u["email"].lower()
        or any(p["policy_number"].lower().startswith(q) for p in u["policies"])
    ]
    return [_user_summary(u) for u in matches[:limit]]


def list_users(limit: int = 100) -> list[dict]:
    return [_user_summary(u) for u in _load()[:limit]]


def get_user_policies(user_id: str) -> list[dict] | None:
    user = get_user_by_id(user_id)
    return user["policies"] if user else None


def get_user_claims(user_id: str) -> list[dict] | None:
    user = get_user_by_id(user_id)
    return user["claims"] if user else None


def build_user_context(user_id: str) -> str:
    """Return a concise text summary of a user's profile for LLM context injection."""
    user = get_user_by_id(user_id)
    if not user:
        return ""

    lines = [
        f"Customer: {user['name']} (ID: {user['id']}, Age: {user['age']})",
        f"Pre-existing conditions: {', '.join(user['pre_existing_conditions'])}",
        "",
        "Active policies:",
    ]
    for p in user["policies"]:
        if p["status"] == "active":
            lines.append(
                f"  - {p['product']} | #{p['policy_number']} | "
                f"{p['trip_type']} | {p['version']} | "
                f"Excess: €{p['excess']} | "
                f"Destinations: {', '.join(p['covered_destinations'])} | "
                f"Valid: {p['start_date']} to {p['end_date']}"
            )

    open_claims = [c for c in user["claims"] if c["status"] in ("pending",)]
    if open_claims:
        lines.append("")
        lines.append("Open claims:")
        for c in open_claims:
            lines.append(
                f"  - {c['claim_id']} | {c['type']} | "
                f"Claimed: €{c['amount_claimed']} | Status: {c['status']}"
            )

    return "\n".join(lines)


def _user_summary(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "age": user["age"],
        "active_policies": [
            {"policy_number": p["policy_number"], "product": p["product"], "type": p["type"]}
            for p in user["policies"] if p["status"] == "active"
        ],
        "open_claims": sum(1 for c in user["claims"] if c["status"] == "pending"),
    }
