"""
Evaluation test cases for the Laya Healthcare KB agent.

Each case has:
  - id: unique identifier
  - category: type of test
  - question: the user query
  - user_id: optional customer ID to inject user context
  - expected_topics: key topics the answer must cover (used by LLM judge)
  - should_contain: strings that must appear in the answer (hard checks)
  - should_not_contain: strings that must NOT appear (hallucination guards)
  - policy_version: expected version referenced ("pre-nov-2025" | "post-nov-2025" | "both" | None)
"""

TEST_CASES = [
    # ── Basic KB retrieval ─────────────────────────────────────────────
    {
        "id": "TC01",
        "category": "kb_retrieval",
        "question": "What is the maximum medical expense cover under the Travel Insurance policy?",
        "user_id": None,
        "expected_topics": ["medical expenses", "coverage limit", "amount"],
        "should_contain": [],
        "should_not_contain": ["I don't know", "cannot find"],
        "policy_version": None,
    },
    {
        "id": "TC02",
        "category": "kb_retrieval",
        "question": "What does the Car Hire Excess Insurance cover?",
        "user_id": None,
        "expected_topics": ["vehicle damage", "excess", "collision damage waiver", "CDW"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },
    {
        "id": "TC03",
        "category": "kb_retrieval",
        "question": "Does the Backpacker Travel Insurance cover adventure sports?",
        "user_id": None,
        "expected_topics": ["backpacker", "sports", "activities", "exclusion"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },
    {
        "id": "TC04",
        "category": "kb_retrieval",
        "question": "What is the excess amount for a single trip car hire policy?",
        "user_id": None,
        "expected_topics": ["excess", "single trip", "car hire", "amount"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },
    {
        "id": "TC05",
        "category": "kb_retrieval",
        "question": "What documents do I need to make a travel insurance claim?",
        "user_id": None,
        "expected_topics": ["claim", "documents", "proof", "procedure"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },

    # ── Policy version disambiguation ──────────────────────────────────
    {
        "id": "TC06",
        "category": "policy_version",
        "question": "What changed in the travel insurance policy after November 2025?",
        "user_id": None,
        "expected_topics": ["November 2025", "policy changes", "new policy", "difference"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": "both",
    },
    {
        "id": "TC07",
        "category": "policy_version",
        "question": "I bought my policy in September 2025. Am I covered for emergency dental treatment?",
        "user_id": None,
        "expected_topics": ["dental", "pre-November 2025", "emergency", "coverage"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": "pre-nov-2025",
    },
    {
        "id": "TC08",
        "category": "policy_version",
        "question": "What is the repatriation procedure for policies issued after November 2025?",
        "user_id": None,
        "expected_topics": ["repatriation", "post-November 2025", "procedure", "authorisation"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": "post-nov-2025",
    },

    # ── Personalised queries (with user context) ───────────────────────
    {
        "id": "TC09",
        "category": "personalised",
        "question": "What is my excess if I need to make a medical claim?",
        "user_id": "USR001",
        "expected_topics": ["excess", "medical", "customer specific", "policy"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },
    {
        "id": "TC10",
        "category": "personalised",
        "question": "Am I covered for a trip to the USA?",
        "user_id": "USR001",
        "expected_topics": ["USA", "destination", "covered", "policy"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },
    {
        "id": "TC11",
        "category": "personalised",
        "question": "I have a heart condition. Does my policy cover pre-existing conditions?",
        "user_id": "USR001",
        "expected_topics": ["pre-existing", "heart condition", "exclusion", "declaration"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },
    {
        "id": "TC12",
        "category": "personalised",
        "question": "Can you summarise my current active policies?",
        "user_id": "USR003",
        "expected_topics": ["active policies", "policy number", "product", "dates"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },
    {
        "id": "TC13",
        "category": "personalised",
        "question": "What is the status of my open claims?",
        "user_id": "USR003",
        "expected_topics": ["claim", "status", "amount", "pending"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },

    # ── Edge cases ─────────────────────────────────────────────────────
    {
        "id": "TC14",
        "category": "edge_case",
        "question": "Does Laya Healthcare offer life insurance?",
        "user_id": None,
        "expected_topics": ["not covered", "outside scope", "travel insurance", "car hire"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },
    {
        "id": "TC15",
        "category": "edge_case",
        "question": "What is the weather like in Dublin?",
        "user_id": None,
        "expected_topics": ["not relevant", "insurance", "out of scope"],
        "should_contain": [],
        "should_not_contain": [],
        "policy_version": None,
    },
]
