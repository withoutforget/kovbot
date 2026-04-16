from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kov.db.base import Base, SoftDeleteMixin, TimestampMixin, UuidPkMixin


class User(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    telegram_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    telegram_username: Mapped[str] = mapped_column(String(64), default="", index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    language: Mapped[str] = mapped_column(String(8), default="ru")

    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False)


class UserProfile(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    interview_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="profile")


class Scenario(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "scenarios"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ScenarioSession(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "scenario_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scenarios.id"))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Dialog(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "dialogs"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), default="")


class Message(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "messages"

    dialog_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dialogs.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user/assistant/system
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class UserAnswer(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user_answers"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scenarios.id"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenario_sessions.id"), nullable=True
    )
    question_key: Mapped[str] = mapped_column(String(128), index=True)
    answer_text: Mapped[str] = mapped_column(Text)


class MoodTrackerEntry(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "mood_tracker_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True, server_default=func.current_date())
    mood_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    factors_down: Mapped[list[str]] = mapped_column(JSON, default=list)
    factors_up: Mapped[list[str]] = mapped_column(JSON, default=list)

    __table_args__ = (UniqueConstraint("user_id", "entry_date", name="uq_mood_user_date"),)


class Habit(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "habits"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class HabitLog(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "habit_logs"

    habit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("habits.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    log_date: Mapped[date] = mapped_column(Date, index=True, server_default=func.current_date())
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("habit_id", "log_date", name="uq_habit_date"),)


class Report(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "reports"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(64), index=True)  # weekly/monthly
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class UserSchedule(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user_schedule"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    schedule_key: Mapped[str] = mapped_column(String(64), index=True)  # mood_tracker/habit_tracker
    at_time: Mapped[time] = mapped_column(Time)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_time_asked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_time_answered: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_time_missed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReminderEvent(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "reminder_events"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    schedule_key: Mapped[str] = mapped_column(String(64), index=True)  # mood_tracker/habit_tracker
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)  # asked/answered/missed
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Document(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "documents"

    original_filename: Mapped[str] = mapped_column(String(512))
    source_uri: Mapped[str] = mapped_column(String(1024), default="")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/pdf")

    title: Mapped[str] = mapped_column(String(512), default="")
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    publisher: Mapped[str] = mapped_column(String(255), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="ru")
    isbn: Mapped[str] = mapped_column(String(64), default="")
    series: Mapped[str] = mapped_column(String(255), default="")
    edition: Mapped[str] = mapped_column(String(255), default="")

    page_count: Mapped[int] = mapped_column(Integer, default=0)
    pdf_type: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    pipeline_version: Mapped[str] = mapped_column(String(32), default="1.0")
    metadata_schema_version: Mapped[str] = mapped_column(String(32), default="1.0")
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_reason: Mapped[str] = mapped_column(Text, default="")

    topic_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    disorder_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(64), default="unknown")


class Chunk(Base, UuidPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), index=True)
    chunk_no: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(32), default="text", index=True)
    block_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    chapter_no: Mapped[str] = mapped_column(String(32), default="")
    chapter_title: Mapped[str] = mapped_column(String(255), default="")
    subchapter_no: Mapped[str] = mapped_column(String(32), default="")
    subchapter_title: Mapped[str] = mapped_column(String(255), default="")
    heading_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    heading_level: Mapped[int] = mapped_column(Integer, default=0)
    page_start: Mapped[int] = mapped_column(Integer, default=0)
    page_end: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[list[int]] = mapped_column(JSON, default=list)
    block_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    topic_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    approach_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_method: Mapped[str] = mapped_column(String(32), default="text_layer")
    chunking_version: Mapped[str] = mapped_column(String(32), default="1.0")
    embedding_model: Mapped[str] = mapped_column(String(128), default="fake-embedder")
    embedding_version: Mapped[str] = mapped_column(String(32), default="1.0")

    __table_args__ = (UniqueConstraint("document_id", "chunk_no", name="uq_chunk_doc_no"),)


class RagRequest(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "rag_requests"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    scenario_id: Mapped[str] = mapped_column(String(64), default="")
    source_channel: Mapped[str] = mapped_column(String(64), default="api")
    user_query: Mapped[str] = mapped_column(Text)
    normalized_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    search_profile: Mapped[str] = mapped_column(String(64), default="quick_advice")
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pipeline_version: Mapped[str] = mapped_column(String(32), default="1.0")


class RagQuery(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "rag_queries"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rag_requests.id"), index=True
    )
    query_id: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text)
    intent_type: Mapped[str] = mapped_column(String(64), default="mixed")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    topic_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    approach_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_content_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_granularity: Mapped[str] = mapped_column(String(32), default="chunk")


class RagResult(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "rag_results"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rag_requests.id"), index=True
    )
    query_id: Mapped[str] = mapped_column(String(64), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id"))
    score_retrieval: Mapped[float] = mapped_column(Float, default=0.0)
    score_rerank: Mapped[float] = mapped_column(Float, default=0.0)
    rank_final: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(32), default="text")
    heading_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    page_start: Mapped[int] = mapped_column(Integer, default=0)
    page_end: Mapped[int] = mapped_column(Integer, default=0)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    text_snippet: Mapped[str] = mapped_column(Text, default="")


class RagContext(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "rag_contexts"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rag_requests.id"), index=True
    )
    seed_chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id"))
    expansion_mode: Mapped[str] = mapped_column(String(32), default="section")
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    chapter_title: Mapped[str] = mapped_column(String(255), default="")
    subchapter_title: Mapped[str] = mapped_column(String(255), default="")
    page_start: Mapped[int] = mapped_column(Integer, default=0)
    page_end: Mapped[int] = mapped_column(Integer, default=0)
    context_text: Mapped[str] = mapped_column(Text, default="")
    context_token_count: Mapped[int] = mapped_column(Integer, default=0)


class LlmCall(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "llm_calls"

    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(64), index=True)  # planner/rerank/answer/chat/entities
    provider: Mapped[str] = mapped_column(String(64), default="openai_compat")
    model: Mapped[str] = mapped_column(String(128), default="")
    prompt: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class TokenUsageEvent(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "token_usage_events"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    telegram_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    telegram_username: Mapped[str] = mapped_column(String(64), default="", index=True)
    source: Mapped[str] = mapped_column(String(64), default="rag_search", index=True)
    model: Mapped[str] = mapped_column(String(128), default="", index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class UserTokenUsageDay(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "user_token_usage_day"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True, server_default=func.current_date())
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_user_token_day"),)
