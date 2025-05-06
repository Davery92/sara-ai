"""Add embedding to message

Revision ID: 303bc56f1fc9
Revises: 5cc1abb6a701
Create Date: 2025-05-05 20:16:27.106667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '303bc56f1fc9'
down_revision: Union[str, None] = '5cc1abb6a701'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
