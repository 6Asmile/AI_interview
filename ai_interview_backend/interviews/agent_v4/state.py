from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict


class InterviewGraphState(TypedDict, total=False):
    """JSON-safe LangGraph state. ORM and file objects are forbidden."""

    schema_version: int
    run_id: str
    thread_id: str
    session_id: str
    question_id: int
    user_id: int
    event: str
    answer_text: str
    answered_count: int
    history: list[dict[str, Any]]
    resume_text: str
    jd_text: str
    media_context: dict[str, Any]
    session_snapshot: dict[str, Any]
    question_text: str
    current_question_plan: dict[str, Any]
    model_config_snapshot: dict[str, Any]
    ai_available: bool
    rule_evaluation: dict[str, Any]
    answer_evaluation: dict[str, Any]
    coverage_summary: dict[str, Any]
    answer_evidence_profile: dict[str, Any]
    question_plan: dict[str, Any]
    retrieval_intent: bool
    rag_context: list[dict[str, Any]]
    retrieval_trace: dict[str, Any]
    generation_context: dict[str, Any]
    generated_text: str
    validation_errors: list[str]
    fallback_reason: str
    generated_question_id: int
    generation_attempt: int
    context_budget: dict[str, Any]
    retrieved_memory_events: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    node_outputs: dict[str, Any]
    node_order: Annotated[list[str], add]
    stream_events: Annotated[list[dict[str, Any]], add]


class InterviewGraphEnvelope(TypedDict):
    """Typed outer channel used by the compatibility graph runner."""

    state: InterviewGraphState
