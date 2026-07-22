from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', validate_assignment=True)


class AgentEvent(str, Enum):
    SUBMIT_ANSWER = 'submit_answer_stream'
    REGENERATE_QUESTION = 'regenerate_next_question'
    FINISH_REPORT = 'finish_report'


class ExecutionStatus(str, Enum):
    ACCEPTED = 'accepted'
    ANSWER_PERSISTED = 'answer_persisted'
    EVALUATING = 'evaluating'
    EVALUATED = 'evaluated'
    GENERATING = 'generating'
    FAILED_RETRYABLE = 'failed_retryable'
    FAILED_TERMINAL = 'failed_terminal'
    PENDING = 'pending'
    RUNNING = 'running'
    WAITING = 'waiting'
    COMPLETED = 'completed'
    DEGRADED = 'degraded'
    FAILED = 'failed'
    CANCELED = 'canceled'


class NextInterviewAction(str, Enum):
    CLARIFY = 'CLARIFY'
    VERIFY = 'VERIFY'
    PROBE = 'PROBE'
    CHALLENGE = 'CHALLENGE'
    TRANSFER = 'TRANSFER'
    ASK_NEW = 'ASK_NEW'
    TRANSITION = 'TRANSITION'
    CANDIDATE_QUESTION = 'CANDIDATE_QUESTION'
    END = 'END'


class AgentTurnInput(StrictContract):
    session_id: UUID
    question_id: int
    user_id: int
    event: AgentEvent
    answer_text: str = Field(min_length=1, max_length=100_000)
    answered_count: int = Field(ge=0, le=200)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    resume_text: str = Field(default='', max_length=200_000)
    jd_text: str = Field(default='', max_length=100_000)
    media_context: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(StrictContract):
    source: Literal['candidate_answer', 'rag']
    quote: str = Field(min_length=1, max_length=2_000)
    supported: bool
    chunk_id: str | None = None

    @model_validator(mode='after')
    def require_rag_chunk(self):
        if self.source == 'rag' and not self.chunk_id:
            raise ValueError('rag evidence requires chunk_id')
        if self.source == 'candidate_answer' and self.chunk_id:
            raise ValueError('candidate answer evidence cannot reference chunk_id')
        return self


class AnswerEvaluation(StrictContract):
    evaluation_mode: Literal['rule_ai', 'rule_ai_dual', 'rule_only', 'rule_only_degraded']
    rule_score: float = Field(ge=0, le=100)
    ai_score: float | None = Field(default=None, ge=0, le=100)
    final_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence_items: list[EvidenceItem] = Field(default_factory=list, max_length=30)
    risk_flags: list[str] = Field(default_factory=list, max_length=30)
    fallback_reason: str = Field(default='', max_length=200)

    @model_validator(mode='after')
    def degraded_mode_has_reason(self):
        if self.evaluation_mode == 'rule_only_degraded' and not self.fallback_reason:
            raise ValueError('degraded evaluation requires fallback_reason')
        return self


class QuestionPlan(StrictContract):
    target_stage: str = Field(min_length=1, max_length=64)
    target_dimension: str = Field(min_length=1, max_length=100)
    target_gap: str = Field(default='', max_length=500)
    difficulty: Literal['easy', 'medium', 'hard']
    next_action: NextInterviewAction
    use_rag: bool
    rag_source_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def sources_match_rag_decision(self):
        if not self.use_rag and self.rag_source_ids:
            raise ValueError('rag_source_ids must be empty when use_rag is false')
        return self


class AgentStreamEvent(StrictContract):
    schema_version: Literal[1] = 1
    event_id: str = Field(min_length=1, max_length=160)
    thread_id: UUID
    run_id: UUID
    type: Literal[
        'run.started', 'node.completed', 'question.delta', 'question.completed',
        'run.degraded', 'run.failed', 'run.completed', 'heartbeat',
        'state.snapshot',
    ]
    sequence: int = Field(ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        return (
            f'id: {self.event_id}\n'
            f'event: {self.type}\n'
            f'data: {self.model_dump_json()}\n\n'
        )
