"""alter embedding column to 1024 dims

Revision ID: 5cc1abb6a701
Revises: 
Create Date: 2025-05-04 09:08:36.401816

"""
from typing import Sequence, Union
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5cc1abb6a701'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Change embedding vector dimension
    op.alter_column(
        "messages",
        "embedding",
        type_=Vector(1024),
        postgresql_using="embedding::vector(1024)"
    )

def downgrade():
    op.alter_column(
        "messages",
        "embedding",
        type_=Vector(768),
        postgresql_using="embedding::vector(768)"
    )
