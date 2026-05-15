from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Increase precision for user_test_attempts.score"""

    def up(self):
        db = self.db.get_db()
        if self._column_exists(db, "user_test_attempts", "score"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts ALTER COLUMN score TYPE NUMERIC(5, 2)"
            )

    def down(self):
        db = self.db.get_db()
        if self._column_exists(db, "user_test_attempts", "score"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts ALTER COLUMN score TYPE NUMERIC(3, 2)"
            )

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
