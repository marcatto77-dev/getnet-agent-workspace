"""Add customer accounts, session revocation and terminal identity fields."""

from alembic import op

revision = "0007_phase10_customer_accounts"
down_revision = "0006_phase9_canonical_routes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
    ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin','tecnico','cliente'));
    ALTER TABLE users ADD COLUMN IF NOT EXISTS customer_id text REFERENCES customers(id) ON DELETE RESTRICT;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password boolean NOT NULL DEFAULT false;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version integer NOT NULL DEFAULT 0;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_users_customer_id ON users(customer_id) WHERE customer_id IS NOT NULL;
    ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_customer_role;
    ALTER TABLE users ADD CONSTRAINT ck_users_customer_role CHECK (
      (role='cliente' AND customer_id IS NOT NULL) OR (role<>'cliente' AND customer_id IS NULL)
    );

    ALTER TABLE customers ADD COLUMN IF NOT EXISTS email text;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS telefone text;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

    ALTER TABLE terminals ADD COLUMN IF NOT EXISTS serial_number text;
    ALTER TABLE terminals ADD COLUMN IF NOT EXISTS apelido text;
    ALTER TABLE terminals ADD COLUMN IF NOT EXISTS installed_at timestamptz;
    UPDATE terminals SET serial_number=id WHERE serial_number IS NULL;
    ALTER TABLE terminals ALTER COLUMN serial_number SET NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_terminals_serial_number ON terminals(serial_number);
    """)


def downgrade():
    op.execute("""
    DELETE FROM users WHERE role='cliente';
    DROP INDEX IF EXISTS uq_terminals_serial_number;
    ALTER TABLE terminals DROP COLUMN IF EXISTS installed_at;
    ALTER TABLE terminals DROP COLUMN IF EXISTS apelido;
    ALTER TABLE terminals DROP COLUMN IF EXISTS serial_number;
    ALTER TABLE customers DROP COLUMN IF EXISTS is_active;
    ALTER TABLE customers DROP COLUMN IF EXISTS telefone;
    ALTER TABLE customers DROP COLUMN IF EXISTS email;
    ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_customer_role;
    DROP INDEX IF EXISTS uq_users_customer_id;
    ALTER TABLE users DROP COLUMN IF EXISTS token_version;
    ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at;
    ALTER TABLE users DROP COLUMN IF EXISTS must_change_password;
    ALTER TABLE users DROP COLUMN IF EXISTS customer_id;
    ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
    ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin','tecnico'));
    """)
