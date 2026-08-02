"""domain tables for senior voice (MySQL-oriented)

Revision ID: 0003_domain_tables
Revises: 0002_create_users
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_domain_tables"
down_revision: str | None = "0002_create_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users: align with domain schema ---
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active")
        )
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "sms_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_ip", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("purpose IN ('login', 'reset_password')", name=op.f("ck_sms_codes_sms_purpose")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sms_codes")),
    )
    op.create_index(op.f("ix_sms_codes_phone"), "sms_codes", ["phone"], unique=False)

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=128), nullable=False),
        sa.Column("device_info", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_auth_sessions_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("refresh_token_hash", name=op.f("uq_auth_sessions_refresh")),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("preferred_lang", sa.String(length=8), nullable=False),
        sa.Column("font_scale", sa.Numeric(3, 2), nullable=False),
        sa.Column("high_contrast", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("preferred_lang IN ('zh', 'en')", name=op.f("ck_user_preferences_pref_lang")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_user_preferences_user")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_preferences")),
    )

    op.create_table(
        "media_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('audio', 'image', 'pdf', 'other')", name=op.f("ck_media_files_media_kind")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_media_files_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_files")),
    )
    op.create_index(op.f("ix_media_files_user_id"), "media_files", ["user_id"], unique=False)

    op.create_table(
        "family_contacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_family_contacts_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_family_contacts")),
    )
    op.create_index(op.f("ix_family_contacts_user_id"), "family_contacts", ["user_id"], unique=False)

    op.create_table(
        "family_push_rules",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("on_record_saved", sa.Boolean(), nullable=False),
        sa.Column("on_abnormal", sa.Boolean(), nullable=False),
        sa.Column("on_visit", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_family_push_rules_user")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_family_push_rules")),
    )

    op.create_table(
        "voice_recognize_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("media_id", sa.String(length=36), nullable=True),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("recognized_text", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("lang IN ('zh', 'en')", name=op.f("ck_voice_recognize_jobs_voice_lang")),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name=op.f("ck_voice_recognize_jobs_voice_status"),
        ),
        sa.ForeignKeyConstraint(["media_id"], ["media_files.id"], name=op.f("fk_voice_jobs_media")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_voice_jobs_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_voice_recognize_jobs")),
    )
    op.create_index(
        op.f("ix_voice_recognize_jobs_user_id"), "voice_recognize_jobs", ["user_id"], unique=False
    )

    op.create_table(
        "qa_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("input_mode", sa.String(length=16), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("audio_media_id", sa.String(length=36), nullable=True),
        sa.Column("voice_job_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("lang IN ('zh', 'en')", name=op.f("ck_qa_sessions_qa_lang")),
        sa.CheckConstraint(
            "input_mode IN ('voice', 'text')", name=op.f("ck_qa_sessions_qa_input_mode")
        ),
        sa.ForeignKeyConstraint(
            ["audio_media_id"], ["media_files.id"], name=op.f("fk_qa_sessions_audio")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_qa_sessions_user")),
        sa.ForeignKeyConstraint(
            ["voice_job_id"], ["voice_recognize_jobs.id"], name=op.f("fk_qa_sessions_voice_job")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qa_sessions")),
    )
    op.create_index(op.f("ix_qa_sessions_user_id"), "qa_sessions", ["user_id"], unique=False)

    op.create_table(
        "qa_recommendations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')", name=op.f("ck_qa_recommendations_risk")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["qa_sessions.id"],
            ondelete="CASCADE",
            name=op.f("fk_qa_reco_session"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_qa_reco_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qa_recommendations")),
        sa.UniqueConstraint("session_id", name=op.f("uq_qa_recommendations_session")),
    )
    op.create_index(
        op.f("ix_qa_recommendations_user_id"), "qa_recommendations", ["user_id"], unique=False
    )

    op.create_table(
        "medical_archives",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=False),
        sa.Column("medicine", sa.Text(), nullable=False),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("raw_ocr_text", sa.Text(), nullable=True),
        sa.Column("image_media_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source IS NULL OR source IN ('camera', 'album')",
            name=op.f("ck_medical_archives_archive_source"),
        ),
        sa.ForeignKeyConstraint(
            ["image_media_id"], ["media_files.id"], name=op.f("fk_medical_archives_image")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_medical_archives_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medical_archives")),
    )
    op.create_index(
        op.f("ix_medical_archives_user_id"), "medical_archives", ["user_id"], unique=False
    )

    op.create_table(
        "archive_ocr_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("image_media_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("medicine", sa.Text(), nullable=True),
        sa.Column("visit_date", sa.Date(), nullable=True),
        sa.Column("raw_ocr_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('camera', 'album')", name=op.f("ck_archive_ocr_jobs_ocr_source")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name=op.f("ck_archive_ocr_jobs_ocr_status"),
        ),
        sa.ForeignKeyConstraint(
            ["image_media_id"], ["media_files.id"], name=op.f("fk_archive_ocr_jobs_image")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_archive_ocr_jobs_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_archive_ocr_jobs")),
    )
    op.create_index(
        op.f("ix_archive_ocr_jobs_user_id"), "archive_ocr_jobs", ["user_id"], unique=False
    )

    op.create_table(
        "health_summaries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=True),
        sa.Column("exam_no", sa.String(length=64), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_health_summaries_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_health_summaries")),
    )
    op.create_index(
        op.f("ix_health_summaries_user_id"), "health_summaries", ["user_id"], unique=False
    )

    op.create_table(
        "health_summary_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("summary_id", sa.String(length=36), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('low', 'medium', 'high')",
            name=op.f("ck_health_summary_items_summary_item_sev"),
        ),
        sa.ForeignKeyConstraint(
            ["summary_id"],
            ["health_summaries.id"],
            ondelete="CASCADE",
            name=op.f("fk_health_summary_items_summary"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_health_summary_items")),
    )
    op.create_index(
        op.f("ix_health_summary_items_summary_id"),
        "health_summary_items",
        ["summary_id"],
        unique=False,
    )

    op.create_table(
        "health_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("patient_name", sa.String(length=64), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=False),
        sa.Column("org_name", sa.String(length=128), nullable=False),
        sa.Column("voucher_no", sa.String(length=64), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("pdf_media_id", sa.String(length=36), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["pdf_media_id"], ["media_files.id"], name=op.f("fk_health_reports_pdf")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_health_reports_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_health_reports")),
    )
    op.create_index(op.f("ix_health_reports_user_id"), "health_reports", ["user_id"], unique=False)

    op.create_table(
        "health_report_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('low', 'medium', 'high')",
            name=op.f("ck_health_report_findings_finding_risk"),
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["health_reports.id"],
            ondelete="CASCADE",
            name=op.f("fk_report_findings_report"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_health_report_findings")),
    )
    op.create_index(
        op.f("ix_health_report_findings_report_id"),
        "health_report_findings",
        ["report_id"],
        unique=False,
    )

    op.create_table(
        "report_glossaries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("term", sa.String(length=64), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_glossaries")),
    )

    op.create_table(
        "archive_shares",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("archive_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("contact_id", sa.String(length=36), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'failed')", name=op.f("ck_archive_shares_share_status")
        ),
        sa.ForeignKeyConstraint(
            ["archive_id"],
            ["medical_archives.id"],
            ondelete="CASCADE",
            name=op.f("fk_archive_shares_archive"),
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["family_contacts.id"], name=op.f("fk_archive_shares_contact")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_archive_shares_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_archive_shares")),
    )
    op.create_index(
        op.f("ix_archive_shares_archive_id"), "archive_shares", ["archive_id"], unique=False
    )

    op.create_table(
        "archive_exports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("archive_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("pdf_media_id", sa.String(length=36), nullable=True),
        sa.Column("download_url", sa.String(length=1024), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed')", name=op.f("ck_archive_exports_export_status")
        ),
        sa.ForeignKeyConstraint(
            ["archive_id"],
            ["medical_archives.id"],
            ondelete="CASCADE",
            name=op.f("fk_archive_exports_archive"),
        ),
        sa.ForeignKeyConstraint(
            ["pdf_media_id"], ["media_files.id"], name=op.f("fk_archive_exports_pdf")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_archive_exports_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_archive_exports")),
    )
    op.create_index(
        op.f("ix_archive_exports_archive_id"), "archive_exports", ["archive_id"], unique=False
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=36), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_archive_exports_archive_id"), table_name="archive_exports")
    op.drop_table("archive_exports")
    op.drop_index(op.f("ix_archive_shares_archive_id"), table_name="archive_shares")
    op.drop_table("archive_shares")
    op.drop_table("report_glossaries")
    op.drop_index(op.f("ix_health_report_findings_report_id"), table_name="health_report_findings")
    op.drop_table("health_report_findings")
    op.drop_index(op.f("ix_health_reports_user_id"), table_name="health_reports")
    op.drop_table("health_reports")
    op.drop_index(op.f("ix_health_summary_items_summary_id"), table_name="health_summary_items")
    op.drop_table("health_summary_items")
    op.drop_index(op.f("ix_health_summaries_user_id"), table_name="health_summaries")
    op.drop_table("health_summaries")
    op.drop_index(op.f("ix_archive_ocr_jobs_user_id"), table_name="archive_ocr_jobs")
    op.drop_table("archive_ocr_jobs")
    op.drop_index(op.f("ix_medical_archives_user_id"), table_name="medical_archives")
    op.drop_table("medical_archives")
    op.drop_index(op.f("ix_qa_recommendations_user_id"), table_name="qa_recommendations")
    op.drop_table("qa_recommendations")
    op.drop_index(op.f("ix_qa_sessions_user_id"), table_name="qa_sessions")
    op.drop_table("qa_sessions")
    op.drop_index(op.f("ix_voice_recognize_jobs_user_id"), table_name="voice_recognize_jobs")
    op.drop_table("voice_recognize_jobs")
    op.drop_table("family_push_rules")
    op.drop_index(op.f("ix_family_contacts_user_id"), table_name="family_contacts")
    op.drop_table("family_contacts")
    op.drop_index(op.f("ix_media_files_user_id"), table_name="media_files")
    op.drop_table("media_files")
    op.drop_table("user_preferences")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index(op.f("ix_sms_codes_phone"), table_name="sms_codes")
    op.drop_table("sms_codes")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("status")
