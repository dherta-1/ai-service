from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Add is_email_verified column to users table if not exists"""

    def up(self):
        db = self.db.get_db()

        # Check if column exists
        result = db.execute_sql("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'is_email_verified'
        """).fetchone()

        if not result:
            # Column doesn't exist, add it
            db.execute_sql("""
                ALTER TABLE users
                ADD COLUMN is_email_verified BOOLEAN DEFAULT FALSE
            """)

    def down(self):
        db = self.db.get_db()

        # Check if column exists before dropping
        result = db.execute_sql("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'is_email_verified'
        """).fetchone()

        if result:
            db.execute_sql("""
                ALTER TABLE users
                DROP COLUMN is_email_verified
            """)
