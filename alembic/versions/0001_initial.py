"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-04-16 11:27:37

"""
from __future__ import annotations

from alembic import op

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None



def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS audit_logs (
	user_id UUID, 
	action VARCHAR(128) NOT NULL, 
	payload JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS documents (
	original_filename VARCHAR(512) NOT NULL, 
	source_uri VARCHAR(1024) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	mime_type VARCHAR(128) NOT NULL, 
	title VARCHAR(512) NOT NULL, 
	authors JSON NOT NULL, 
	publisher VARCHAR(255) NOT NULL, 
	year INTEGER, 
	language VARCHAR(8) NOT NULL, 
	isbn VARCHAR(64) NOT NULL, 
	series VARCHAR(255) NOT NULL, 
	edition VARCHAR(255) NOT NULL, 
	page_count INTEGER NOT NULL, 
	pdf_type VARCHAR(32) NOT NULL, 
	ocr_used BOOLEAN NOT NULL, 
	pipeline_version VARCHAR(32) NOT NULL, 
	metadata_schema_version VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	last_processed_at TIMESTAMP WITH TIME ZONE, 
	error_reason TEXT NOT NULL, 
	topic_tags JSON NOT NULL, 
	disorder_tags JSON NOT NULL, 
	source_type VARCHAR(64) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS llm_calls (
	request_id UUID, 
	purpose VARCHAR(64) NOT NULL, 
	provider VARCHAR(64) NOT NULL, 
	model VARCHAR(128) NOT NULL, 
	prompt JSON NOT NULL, 
	response JSON NOT NULL, 
	error TEXT NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS scenarios (
	key VARCHAR(64) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS users (
	telegram_user_id VARCHAR(64) NOT NULL, 
	timezone VARCHAR(64) NOT NULL, 
	language VARCHAR(8) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS chunks (
	document_id UUID NOT NULL, 
	chunk_no INTEGER NOT NULL, 
	text TEXT NOT NULL, 
	content_type VARCHAR(32) NOT NULL, 
	block_types JSON NOT NULL, 
	chapter_no VARCHAR(32) NOT NULL, 
	chapter_title VARCHAR(255) NOT NULL, 
	subchapter_no VARCHAR(32) NOT NULL, 
	subchapter_title VARCHAR(255) NOT NULL, 
	heading_path JSON NOT NULL, 
	heading_level INTEGER NOT NULL, 
	page_start INTEGER NOT NULL, 
	page_end INTEGER NOT NULL, 
	pages JSON NOT NULL, 
	block_ids JSON NOT NULL, 
	topic_tags JSON NOT NULL, 
	approach_tags JSON NOT NULL, 
	risk_tags JSON NOT NULL, 
	char_count INTEGER NOT NULL, 
	token_count INTEGER NOT NULL, 
	ocr_used BOOLEAN NOT NULL, 
	extraction_method VARCHAR(32) NOT NULL, 
	chunking_version VARCHAR(32) NOT NULL, 
	embedding_model VARCHAR(128) NOT NULL, 
	embedding_version VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_chunk_doc_no UNIQUE (document_id, chunk_no), 
	FOREIGN KEY(document_id) REFERENCES documents (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS dialogs (
	user_id UUID NOT NULL, 
	scenario_id UUID, 
	title VARCHAR(255) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(scenario_id) REFERENCES scenarios (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS habits (
	user_id UUID NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	archived BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS mood_tracker_entries (
	user_id UUID NOT NULL, 
	entry_date DATE DEFAULT CURRENT_DATE NOT NULL, 
	mood_score INTEGER, 
	notes TEXT NOT NULL, 
	factors_down JSON NOT NULL, 
	factors_up JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_mood_user_date UNIQUE (user_id, entry_date), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS rag_requests (
	user_id UUID, 
	scenario_id VARCHAR(64) NOT NULL, 
	source_channel VARCHAR(64) NOT NULL, 
	user_query TEXT NOT NULL, 
	normalized_state JSON NOT NULL, 
	search_profile VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	pipeline_version VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS reminder_events (
	user_id UUID NOT NULL, 
	schedule_key VARCHAR(64) NOT NULL, 
	asked_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	answered_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(16) NOT NULL, 
	meta JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS reports (
	user_id UUID NOT NULL, 
	report_type VARCHAR(64) NOT NULL, 
	period_start DATE NOT NULL, 
	period_end DATE NOT NULL, 
	content JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS scenario_sessions (
	user_id UUID NOT NULL, 
	scenario_id UUID NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	state JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(scenario_id) REFERENCES scenarios (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS user_profiles (
	user_id UUID NOT NULL, 
	interview_summary TEXT, 
	data JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS user_schedule (
	user_id UUID NOT NULL, 
	schedule_key VARCHAR(64) NOT NULL, 
	at_time TIME WITHOUT TIME ZONE NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	last_time_asked TIMESTAMP WITH TIME ZONE, 
	last_time_answered TIMESTAMP WITH TIME ZONE, 
	last_time_missed TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)"""
    )

    # Backward-compatible evolution if user_schedule existed before Alembic:
    op.execute("ALTER TABLE user_schedule ADD COLUMN IF NOT EXISTS last_time_answered TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE user_schedule ADD COLUMN IF NOT EXISTS last_time_missed TIMESTAMPTZ NULL")

    op.execute(
        """
CREATE TABLE IF NOT EXISTS habit_logs (
	habit_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	log_date DATE DEFAULT CURRENT_DATE NOT NULL, 
	done BOOLEAN NOT NULL, 
	notes TEXT NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_habit_date UNIQUE (habit_id, log_date), 
	FOREIGN KEY(habit_id) REFERENCES habits (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS messages (
	dialog_id UUID NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	text TEXT NOT NULL, 
	meta JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(dialog_id) REFERENCES dialogs (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS rag_contexts (
	request_id UUID NOT NULL, 
	seed_chunk_id UUID NOT NULL, 
	expansion_mode VARCHAR(32) NOT NULL, 
	document_id UUID NOT NULL, 
	chapter_title VARCHAR(255) NOT NULL, 
	subchapter_title VARCHAR(255) NOT NULL, 
	page_start INTEGER NOT NULL, 
	page_end INTEGER NOT NULL, 
	context_text TEXT NOT NULL, 
	context_token_count INTEGER NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES rag_requests (id), 
	FOREIGN KEY(seed_chunk_id) REFERENCES chunks (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS rag_queries (
	request_id UUID NOT NULL, 
	query_id VARCHAR(64) NOT NULL, 
	text TEXT NOT NULL, 
	intent_type VARCHAR(64) NOT NULL, 
	weight FLOAT NOT NULL, 
	topic_tags JSON NOT NULL, 
	approach_tags JSON NOT NULL, 
	preferred_content_types JSON NOT NULL, 
	expected_granularity VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES rag_requests (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS rag_results (
	request_id UUID NOT NULL, 
	query_id VARCHAR(64) NOT NULL, 
	document_id UUID NOT NULL, 
	chunk_id UUID NOT NULL, 
	score_retrieval FLOAT NOT NULL, 
	score_rerank FLOAT NOT NULL, 
	rank_final INTEGER NOT NULL, 
	content_type VARCHAR(32) NOT NULL, 
	heading_path JSON NOT NULL, 
	page_start INTEGER NOT NULL, 
	page_end INTEGER NOT NULL, 
	ocr_used BOOLEAN NOT NULL, 
	text_snippet TEXT NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES rag_requests (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id), 
	FOREIGN KEY(chunk_id) REFERENCES chunks (id)
)"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS user_answers (
	user_id UUID NOT NULL, 
	scenario_id UUID NOT NULL, 
	session_id UUID, 
	question_key VARCHAR(128) NOT NULL, 
	answer_text TEXT NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(scenario_id) REFERENCES scenarios (id), 
	FOREIGN KEY(session_id) REFERENCES scenario_sessions (id)
)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_documents_pdf_type ON documents (pdf_type)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_documents_sha256 ON documents (sha256)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_documents_status ON documents (status)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_llm_calls_purpose ON llm_calls (purpose)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_llm_calls_request_id ON llm_calls (request_id)"""
    )

    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ix_scenarios_key ON scenarios (key)"""
    )

    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_user_id ON users (telegram_user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_chunks_chunk_no ON chunks (chunk_no)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_chunks_content_type ON chunks (content_type)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_chunks_document_id ON chunks (document_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_dialogs_user_id ON dialogs (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_habits_user_id ON habits (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_mood_tracker_entries_entry_date ON mood_tracker_entries (entry_date)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_mood_tracker_entries_user_id ON mood_tracker_entries (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_rag_requests_status ON rag_requests (status)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_reminder_events_asked_at ON reminder_events (asked_at)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_reminder_events_schedule_key ON reminder_events (schedule_key)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_reminder_events_status ON reminder_events (status)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_reminder_events_user_id ON reminder_events (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_reports_report_type ON reports (report_type)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_reports_user_id ON reports (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_scenario_sessions_status ON scenario_sessions (status)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_scenario_sessions_user_id ON scenario_sessions (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_user_profiles_user_id ON user_profiles (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_user_schedule_enabled ON user_schedule (enabled)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_user_schedule_schedule_key ON user_schedule (schedule_key)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_user_schedule_user_id ON user_schedule (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_habit_logs_habit_id ON habit_logs (habit_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_habit_logs_log_date ON habit_logs (log_date)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_habit_logs_user_id ON habit_logs (user_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_messages_dialog_id ON messages (dialog_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_rag_contexts_request_id ON rag_contexts (request_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_rag_queries_query_id ON rag_queries (query_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_rag_queries_request_id ON rag_queries (request_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_rag_results_query_id ON rag_results (query_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_rag_results_request_id ON rag_results (request_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_user_answers_question_key ON user_answers (question_key)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_user_answers_scenario_id ON user_answers (scenario_id)"""
    )

    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_user_answers_user_id ON user_answers (user_id)"""
    )



def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_answers_user_id")
    op.execute("DROP INDEX IF EXISTS ix_user_answers_scenario_id")
    op.execute("DROP INDEX IF EXISTS ix_user_answers_question_key")
    op.execute("DROP INDEX IF EXISTS ix_rag_results_request_id")
    op.execute("DROP INDEX IF EXISTS ix_rag_results_query_id")
    op.execute("DROP INDEX IF EXISTS ix_rag_queries_request_id")
    op.execute("DROP INDEX IF EXISTS ix_rag_queries_query_id")
    op.execute("DROP INDEX IF EXISTS ix_rag_contexts_request_id")
    op.execute("DROP INDEX IF EXISTS ix_messages_dialog_id")
    op.execute("DROP INDEX IF EXISTS ix_habit_logs_user_id")
    op.execute("DROP INDEX IF EXISTS ix_habit_logs_log_date")
    op.execute("DROP INDEX IF EXISTS ix_habit_logs_habit_id")
    op.execute("DROP INDEX IF EXISTS ix_user_schedule_user_id")
    op.execute("DROP INDEX IF EXISTS ix_user_schedule_schedule_key")
    op.execute("DROP INDEX IF EXISTS ix_user_schedule_enabled")
    op.execute("DROP INDEX IF EXISTS ix_user_profiles_user_id")
    op.execute("DROP INDEX IF EXISTS ix_scenario_sessions_user_id")
    op.execute("DROP INDEX IF EXISTS ix_scenario_sessions_status")
    op.execute("DROP INDEX IF EXISTS ix_reports_user_id")
    op.execute("DROP INDEX IF EXISTS ix_reports_report_type")
    op.execute("DROP INDEX IF EXISTS ix_reminder_events_user_id")
    op.execute("DROP INDEX IF EXISTS ix_reminder_events_status")
    op.execute("DROP INDEX IF EXISTS ix_reminder_events_schedule_key")
    op.execute("DROP INDEX IF EXISTS ix_reminder_events_asked_at")
    op.execute("DROP INDEX IF EXISTS ix_rag_requests_status")
    op.execute("DROP INDEX IF EXISTS ix_mood_tracker_entries_user_id")
    op.execute("DROP INDEX IF EXISTS ix_mood_tracker_entries_entry_date")
    op.execute("DROP INDEX IF EXISTS ix_habits_user_id")
    op.execute("DROP INDEX IF EXISTS ix_dialogs_user_id")
    op.execute("DROP INDEX IF EXISTS ix_chunks_document_id")
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_type")
    op.execute("DROP INDEX IF EXISTS ix_chunks_chunk_no")
    op.execute("DROP INDEX IF EXISTS ix_users_telegram_user_id")
    op.execute("DROP INDEX IF EXISTS ix_scenarios_key")
    op.execute("DROP INDEX IF EXISTS ix_llm_calls_request_id")
    op.execute("DROP INDEX IF EXISTS ix_llm_calls_purpose")
    op.execute("DROP INDEX IF EXISTS ix_documents_status")
    op.execute("DROP INDEX IF EXISTS ix_documents_sha256")
    op.execute("DROP INDEX IF EXISTS ix_documents_pdf_type")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_user_id")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_action")

    op.execute("DROP TABLE IF EXISTS user_answers CASCADE")
    op.execute("DROP TABLE IF EXISTS rag_results CASCADE")
    op.execute("DROP TABLE IF EXISTS rag_queries CASCADE")
    op.execute("DROP TABLE IF EXISTS rag_contexts CASCADE")
    op.execute("DROP TABLE IF EXISTS messages CASCADE")
    op.execute("DROP TABLE IF EXISTS habit_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS user_schedule CASCADE")
    op.execute("DROP TABLE IF EXISTS user_profiles CASCADE")
    op.execute("DROP TABLE IF EXISTS scenario_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS reports CASCADE")
    op.execute("DROP TABLE IF EXISTS reminder_events CASCADE")
    op.execute("DROP TABLE IF EXISTS rag_requests CASCADE")
    op.execute("DROP TABLE IF EXISTS mood_tracker_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS habits CASCADE")
    op.execute("DROP TABLE IF EXISTS dialogs CASCADE")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS scenarios CASCADE")
    op.execute("DROP TABLE IF EXISTS llm_calls CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE")
