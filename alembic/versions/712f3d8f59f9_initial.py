"""initial

Revision ID: 712f3d8f59f9
Revises: 
Create Date: 2026-03-12 03:09:41.972228

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "712f3d8f59f9"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
