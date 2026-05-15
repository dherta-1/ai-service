from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Add status and timing fields to user_test_attempts"""

    def up(self):
        db = self.db.get_db()

        if not self._column_exists(db, "user_test_attempts", "status"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts ADD COLUMN status SMALLINT DEFAULT 0"
            )

        if not self._column_exists(db, "user_test_attempts", "started_at"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts ADD COLUMN started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )

        if not self._column_exists(db, "user_test_attempts", "submitted_at"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts ADD COLUMN submitted_at TIMESTAMP NULL"
            )

    def down(self):
        db = self.db.get_db()

        if self._column_exists(db, "user_test_attempts", "submitted_at"):
            db.execute_sql("ALTER TABLE user_test_attempts DROP COLUMN submitted_at")

        if self._column_exists(db, "user_test_attempts", "started_at"):
            db.execute_sql("ALTER TABLE user_test_attempts DROP COLUMN started_at")

        if self._column_exists(db, "user_test_attempts", "status"):
            db.execute_sql("ALTER TABLE user_test_attempts DROP COLUMN status")

    @staticmethod
    def _column_exists(db, table: str, column: str) -> bool:
        result = db.execute_sql(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            (table, column),
        ).fetchone()
        return result is not None
