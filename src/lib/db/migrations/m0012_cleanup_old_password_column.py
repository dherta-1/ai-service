from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Remove old hash_password column, keep password_hash"""

    def up(self):
        db = self.db.get_db()

        # Check if old hash_password column exists
        result = db.execute_sql("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'hash_password'
        """).fetchone()

        if result:
            db.execute_sql("""
                ALTER TABLE users
                DROP COLUMN hash_password
            """)

    def down(self):
        db = self.db.get_db()

        # Check if hash_password exists before adding back
        result = db.execute_sql("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'hash_password'
        """).fetchone()

        if not result:
            db.execute_sql("""
                ALTER TABLE users
                ADD COLUMN hash_password VARCHAR(255)
            """)
