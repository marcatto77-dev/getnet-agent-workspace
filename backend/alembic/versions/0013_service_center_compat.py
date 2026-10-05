"""Keep legacy handoff inserts compatible while preserving FIFO metadata."""
from alembic import op

revision = "0013_service_center_compat"
down_revision = "0012_service_center"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE handoffs ALTER COLUMN waiting_since SET DEFAULT now()")

def downgrade():
    op.execute("ALTER TABLE handoffs ALTER COLUMN waiting_since DROP DEFAULT")
