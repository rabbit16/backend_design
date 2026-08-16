"""empty revision already applied; visit_no is in 0005

Revision ID: 07b6367542dc
Revises: 880b6b63d119
Create Date: 2026-08-03 12:41:08.723768
"""

from __future__ import annotations

from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "07b6367542dc"
down_revision: str | None = "880b6b63d119"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 此版本此前已 stamp 到现网库，upgrade 体为空。就诊号列见 0005_archive_visit_no。
    pass


def downgrade() -> None:
    pass
