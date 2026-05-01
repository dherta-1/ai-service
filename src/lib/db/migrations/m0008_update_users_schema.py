from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Update users table: add password_hash, fix is_email_verified to BOOLEAN, drop reset_password_token, add email_verification_sent_at"""

    def up(self):
        db = self.db.get_db()
        db.execute_sql("""
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255),
                ADD COLUMN IF NOT EXISTS email_verification_sent_at TIMESTAMP
        """)

        # Check if is_email_verified exists and is not already BOOLEAN
        result = db.execute_sql("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'is_email_verified'
        """).fetchone()

        if result:
            col_name, col_type = result
            # Only convert if it's not already BOOLEAN
            if col_type != 'boolean':
                db.execute_sql("""
                    ALTER TABLE users
                        ALTER COLUMN is_email_verified TYPE BOOLEAN
                        USING (is_email_verified = 'true')
                """)
                db.execute_sql("""
                    ALTER TABLE users
                        ALTER COLUMN is_email_verified SET DEFAULT FALSE
                """)

        db.execute_sql("""
            ALTER TABLE users
                DROP COLUMN IF EXISTS reset_password_token
        """)

    def down(self):
        db = self.db.get_db()
        db.execute_sql("""
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS reset_password_token VARCHAR(50)
        """)

        # Check if is_email_verified is BOOLEAN before converting back
        result = db.execute_sql("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'is_email_verified'
        """).fetchone()

        if result:
            col_name, col_type = result
            # Only convert if it's BOOLEAN
            if col_type == 'boolean':
                db.execute_sql("""
                    ALTER TABLE users
                        ALTER COLUMN is_email_verified TYPE VARCHAR(5)
                        USING (CASE WHEN is_email_verified THEN 'true' ELSE 'false' END)
                """)

        db.execute_sql("""
            ALTER TABLE users
                DROP COLUMN IF EXISTS password_hash,
                DROP COLUMN IF EXISTS email_verification_sent_at
        """)
