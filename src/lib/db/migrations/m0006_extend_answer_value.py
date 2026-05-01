from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Change answer.value from VARCHAR(512) to TEXT to support longer answer texts."""

    def up(self):
        db = self.db.get_db()
        db.execute_sql("""
            ALTER TABLE answers
            ALTER COLUMN value TYPE TEXT
        """)

    def down(self):
        db = self.db.get_db()
        db.execute_sql("""
            ALTER TABLE answers
            ALTER COLUMN value TYPE VARCHAR(512)
        """)
