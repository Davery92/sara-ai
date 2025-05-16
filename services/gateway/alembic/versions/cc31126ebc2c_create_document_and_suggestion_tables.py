"""create_document_and_suggestion_tables

Revision ID: cc31126ebc2c
Revises: 303bc56f1fc9
Create Date: 2025-05-15 12:57:46.269959

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc31126ebc2c'
down_revision: Union[str, None] = '303bc56f1fc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
