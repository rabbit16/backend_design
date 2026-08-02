"""qa multi-turn messages

Revision ID: 0004_qa_multi_turn
Revises: 0003_domain_tables
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_qa_multi_turn"
down_revision: str | None = "0003_domain_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "qa_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("input_mode", sa.String(length=16), nullable=True),
        sa.Column("audio_media_id", sa.String(length=36), nullable=True),
        sa.Column("voice_job_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')", name=op.f("ck_qa_messages_qa_msg_role")
        ),
        sa.CheckConstraint(
            "input_mode IS NULL OR input_mode IN ('voice', 'text')",
            name=op.f("ck_qa_messages_qa_msg_input_mode"),
        ),
        sa.ForeignKeyConstraint(
            ["audio_media_id"], ["media_files.id"], name=op.f("fk_qa_messages_audio")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["qa_sessions.id"],
            ondelete="CASCADE",
            name=op.f("fk_qa_messages_session"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_qa_messages_user")),
        sa.ForeignKeyConstraint(
            ["voice_job_id"], ["voice_recognize_jobs.id"], name=op.f("fk_qa_messages_voice_job")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qa_messages")),
        sa.UniqueConstraint("session_id", "turn_index", name=op.f("uq_qa_messages_session_turn")),
    )
    op.create_index(op.f("ix_qa_messages_session_id"), "qa_messages", ["session_id"], unique=False)
    op.create_index(op.f("ix_qa_messages_user_id"), "qa_messages", ["user_id"], unique=False)

    with op.batch_alter_table("qa_sessions") as batch:
        batch.add_column(sa.Column("title", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active")
        )
        batch.add_column(
            sa.Column("message_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch.drop_constraint(op.f("fk_qa_sessions_audio"), type_="foreignkey")
        batch.drop_constraint(op.f("fk_qa_sessions_voice_job"), type_="foreignkey")
        batch.drop_column("question_text")
        batch.drop_column("answer_text")
        batch.drop_column("audio_media_id")
        batch.drop_column("voice_job_id")
        batch.drop_column("input_mode")


def downgrade() -> None:
    with op.batch_alter_table("qa_sessions") as batch:
        batch.add_column(sa.Column("input_mode", sa.String(length=16), nullable=False, server_default="voice"))
        batch.add_column(sa.Column("voice_job_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("audio_media_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("answer_text", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("question_text", sa.Text(), nullable=False, server_default=""))
        batch.create_foreign_key(
            op.f("fk_qa_sessions_voice_job"), "voice_recognize_jobs", ["voice_job_id"], ["id"]
        )
        batch.create_foreign_key(
            op.f("fk_qa_sessions_audio"), "media_files", ["audio_media_id"], ["id"]
        )
        batch.drop_column("updated_at")
        batch.drop_column("last_message_at")
        batch.drop_column("message_count")
        batch.drop_column("status")
        batch.drop_column("title")

    op.drop_index(op.f("ix_qa_messages_user_id"), table_name="qa_messages")
    op.drop_index(op.f("ix_qa_messages_session_id"), table_name="qa_messages")
    op.drop_table("qa_messages")
