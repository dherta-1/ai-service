from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Create audit_logs table"""

    def up(self):
        db = self.db.get_db()
        db.execute_sql("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                actor_type VARCHAR(50) NOT NULL,
                actor_id UUID,
                entity_type VARCHAR(100) NOT NULL,
                entity_id UUID,
                action_type VARCHAR(50) NOT NULL,
                before_data TEXT,
                after_data TEXT,
                request_ip VARCHAR(100),
                client VARCHAR(255),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        db.execute_sql("CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_id ON audit_logs (actor_id)")
        db.execute_sql("CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_type ON audit_logs (entity_type)")
        db.execute_sql("CREATE INDEX IF NOT EXISTS ix_audit_logs_action_type ON audit_logs (action_type)")
        db.execute_sql("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at)")

    def down(self):
        db = self.db.get_db()
        db.execute_sql("DROP TABLE IF EXISTS audit_logs")
