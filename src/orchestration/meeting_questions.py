"""Central meeting-question catalog and answer-matrix helpers.

This module provides stable ``question_id`` values and deterministic task-to-
question mappings used by routing and run-level state tracking.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


MEETING_QUESTION_REGISTRY: dict[str, dict[str, Any]] = {
    "q_company_fundamentals": {
        "question": "What are the verified company fundamentals (identity, offering, footprint, leadership, business model)?",
        "focus_area": "company_profile",
    },
    "q_economic_commercial_situation": {
        "question": "What public signals show economic or commercial pressure, growth, contraction, or strategic change?",
        "focus_area": "company_profile",
    },
    "q_financial_deep_dive": {
        "question": "Which balance-sheet, inventory, debt, and working-capital facts are supported by primary financial evidence?",
        "focus_area": "company_profile",
    },
    "q_market_situation": {
        "question": "How does the market currently evolve (demand, supply pressure, overcapacity, growth/decline) and why?",
        "focus_area": "industry_analysis",
    },
    "q_peer_companies": {
        "question": "Which peer companies are direct or close competitors for the same or similar goods?",
        "focus_area": "market_network",
    },
    "q_product_asset_scope": {
        "question": "Which products/assets/materials are in scope and most relevant for buyer or redeployment analysis?",
        "focus_area": "company_profile",
    },
    "q_transaction_event_intelligence": {
        "question": "Which strategic events, carve-outs, restructurings, or regulatory disclosures materially change the opportunity picture?",
        "focus_area": "company_profile",
    },
    "q_monetization_redeployment": {
        "question": "Which monetization and redeployment paths are plausible, including relevant buyers and fit?",
        "focus_area": "market_network",
    },
    "q_liquisto_opportunity_assessment": {
        "question": "Is an excess-inventory opportunity best supported by current evidence, and why?",
        "focus_area": "synthesis",
    },
    "q_negotiation_relevance": {
        "question": "Which signals are most relevant for negotiation angle, urgency, pricing power, and next steps?",
        "focus_area": "synthesis",
    },
    "q_contact_intelligence": {
        "question": "Which target contacts are discoverable/qualified at prioritized buyer firms, and what outreach angles are plausible?",
        "focus_area": "contact_intelligence",
    },
    "q_target_company_contacts": {
        "question": "Which stakeholders at the target company itself are the best entry points for an inventory-to-cash discussion?",
        "focus_area": "contact_intelligence",
    },
}


TASK_TO_QUESTION_IDS: dict[str, tuple[str, ...]] = {
    "company_fundamentals": ("q_company_fundamentals",),
    "economic_commercial_situation": ("q_economic_commercial_situation",),
    "financial_deep_dive": ("q_financial_deep_dive",),
    "market_situation": ("q_market_situation",),
    "peer_companies": ("q_peer_companies",),
    "product_asset_scope": ("q_product_asset_scope",),
    "transaction_event_intelligence": ("q_transaction_event_intelligence",),
    "monetization_redeployment": ("q_monetization_redeployment",),
    "contact_discovery": ("q_contact_intelligence",),
    "target_company_contacts": ("q_target_company_contacts",),
    "contact_qualification": ("q_contact_intelligence",),
    "liquisto_opportunity_assessment": ("q_liquisto_opportunity_assessment",),
    "negotiation_relevance": ("q_negotiation_relevance",),
}


def question_ids_for_task(task_key: str) -> tuple[str, ...]:
    """Return deterministic question-id coverage for a task_key."""
    return TASK_TO_QUESTION_IDS.get(task_key, ())


def build_question_registry() -> dict[str, dict[str, Any]]:
    """Create a run-local copy of the central question registry."""
    return deepcopy(MEETING_QUESTION_REGISTRY)


def build_initial_answer_matrix() -> dict[str, dict[str, Any]]:
    """Create a pending answer matrix for all known questions."""
    matrix: dict[str, dict[str, Any]] = {}
    for question_id, meta in MEETING_QUESTION_REGISTRY.items():
        matrix[question_id] = {
            "status": "pending",
            "answer": "",
            "notes": "",
            "source_tasks": [],
            "target_section": meta.get("focus_area", "n/v"),
        }
    return matrix


def matrix_status_for_task_status(task_status: str) -> str:
    """Normalize task lifecycle statuses to answer-matrix statuses."""
    if task_status == "accepted":
        return "answered"
    if task_status in {"degraded", "blocked"}:
        return "partially_answered"
    if task_status == "skipped":
        return "blocked"
    return "pending"
