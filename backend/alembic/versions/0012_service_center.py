"""Service-center state, immutable handoff events and internal notes."""
from alembic import op

revision = "0012_service_center"
down_revision = "0011_phase14_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS waiting_since timestamptz;
    ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS claimed_at timestamptz;
    ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS first_response_at timestamptz;
    ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS closed_by_id integer REFERENCES users(id);
    ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS close_category varchar(30);
    ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
    UPDATE handoffs SET waiting_since=COALESCE(waiting_since,created_at) WHERE waiting_since IS NULL;
    ALTER TABLE handoffs ALTER COLUMN waiting_since SET NOT NULL;
    ALTER TABLE messages ADD COLUMN IF NOT EXISTS visibility varchar(12) NOT NULL DEFAULT 'public';
    ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_visibility_check;
    ALTER TABLE messages ADD CONSTRAINT messages_visibility_check CHECK (visibility IN ('public','internal'));
    CREATE TABLE IF NOT EXISTS handoff_events (
      id uuid PRIMARY KEY, handoff_id uuid NOT NULL REFERENCES handoffs(id) ON DELETE CASCADE,
      type varchar(30) NOT NULL, actor_id integer REFERENCES users(id),
      from_technician_id integer REFERENCES users(id), to_technician_id integer REFERENCES users(id),
      note text, created_at timestamptz NOT NULL DEFAULT now()
    );
    INSERT INTO handoff_events(id,handoff_id,type,to_technician_id,created_at)
      SELECT gen_random_uuid(),h.id,CASE WHEN h.status='assigned' THEN 'auto_assigned' WHEN h.status='closed' THEN 'closed' ELSE 'created' END,h.technician_id,h.created_at
      FROM handoffs h WHERE NOT EXISTS (SELECT 1 FROM handoff_events e WHERE e.handoff_id=h.id);
    CREATE INDEX IF NOT EXISTS handoffs_center_waiting_idx ON handoffs(status,waiting_since,id);
    CREATE INDEX IF NOT EXISTS handoffs_center_technician_idx ON handoffs(technician_id,status,closed_at);
    CREATE INDEX IF NOT EXISTS handoff_events_handoff_idx ON handoff_events(handoff_id,created_at);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS handoff_events; ALTER TABLE messages DROP COLUMN IF EXISTS visibility; ALTER TABLE handoffs DROP COLUMN IF EXISTS version, DROP COLUMN IF EXISTS close_category, DROP COLUMN IF EXISTS closed_by_id, DROP COLUMN IF EXISTS first_response_at, DROP COLUMN IF EXISTS claimed_at, DROP COLUMN IF EXISTS waiting_since;")
