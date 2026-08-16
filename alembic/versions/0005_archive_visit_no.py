"""add visit_no to medical archives and ocr jobs

Revision ID: 0005_archive_visit_no
Revises: 07b6367542dc
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005_archive_visit_no"
down_revision: str | None = "07b6367542dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _mysql_has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table
              AND COLUMN_NAME = :column
            """
        ),
        {"table": table, "column": column},
    ).scalar()
    return bool(row)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        if not _mysql_has_column("medical_archives", "visit_no"):
            op.add_column(
                "medical_archives",
                sa.Column("visit_no", sa.String(length=64), nullable=True),
            )
        if not _mysql_has_column("archive_ocr_jobs", "visit_no"):
            op.add_column(
                "archive_ocr_jobs",
                sa.Column("visit_no", sa.String(length=64), nullable=True),
            )
        op.execute(
            sa.text(
                """
                UPDATE medical_archives
                SET visit_no = CONCAT(
                    'MZ',
                    DATE_FORMAT(visit_date, '%Y%m%d'),
                    UPPER(SUBSTRING(REPLACE(id, '-', ''), 1, 6))
                )
                WHERE visit_no IS NULL OR visit_no = ''
                """
            )
        )
        op.alter_column(
            "medical_archives",
            "visit_no",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        if not _mysql_has_column("medical_archives", "active_visit_no"):
            op.execute(
                sa.text(
                    """
                    ALTER TABLE medical_archives
                    ADD COLUMN active_visit_no CHAR(64) GENERATED ALWAYS AS (
                        IF(deleted_at IS NULL, visit_no, NULL)
                    ) STORED
                    """
                )
            )
        indexes = {
            row[0]
            for row in bind.execute(
                sa.text(
                    """
                    SELECT INDEX_NAME
                    FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'medical_archives'
                    """
                )
            )
        }
        if "uq_medical_archives_user_active_visit" not in indexes:
            op.create_index(
                "uq_medical_archives_user_active_visit",
                "medical_archives",
                ["user_id", "active_visit_no"],
                unique=True,
            )
        return

    with op.batch_alter_table("medical_archives") as batch:
        batch.add_column(sa.Column("visit_no", sa.String(length=64), nullable=True))
    with op.batch_alter_table("archive_ocr_jobs") as batch:
        batch.add_column(sa.Column("visit_no", sa.String(length=64), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE medical_archives
            SET visit_no = 'MZ' || strftime('%Y%m%d', visit_date)
                || substr(replace(id, '-', ''), 1, 6)
            WHERE visit_no IS NULL OR visit_no = ''
            """
        )
    )
    with op.batch_alter_table("medical_archives") as batch:
        batch.alter_column(
            "visit_no",
            existing_type=sa.String(length=64),
            nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        indexes = {
            row[0]
            for row in bind.execute(
                sa.text(
                    """
                    SELECT INDEX_NAME
                    FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'medical_archives'
                    """
                )
            )
        }
        if "uq_medical_archives_user_active_visit" in indexes:
            op.drop_index(
                "uq_medical_archives_user_active_visit",
                table_name="medical_archives",
            )
        if _mysql_has_column("medical_archives", "active_visit_no"):
            op.execute(sa.text("ALTER TABLE medical_archives DROP COLUMN active_visit_no"))
        if _mysql_has_column("archive_ocr_jobs", "visit_no"):
            op.drop_column("archive_ocr_jobs", "visit_no")
        if _mysql_has_column("medical_archives", "visit_no"):
            op.drop_column("medical_archives", "visit_no")
        return

    with op.batch_alter_table("archive_ocr_jobs") as batch:
        batch.drop_column("visit_no")
    with op.batch_alter_table("medical_archives") as batch:
        batch.drop_column("visit_no")
