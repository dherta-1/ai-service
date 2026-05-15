from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Ensure exam_template_id column exists in user_test_attempts"""

    def up(self):
        db = self.db.get_db()
        # If exam_test_id exists, rename it to exam_template_id
        if self._column_exists(db, "user_test_attempts", "exam_test_id"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts RENAME COLUMN exam_test_id TO exam_template_id"
            )
        # If neither exists, add exam_template_id (for new databases)
        elif not self._column_exists(db, "user_test_attempts", "exam_template_id"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts ADD COLUMN exam_template_id VARCHAR(255) NOT NULL DEFAULT ''"
            )

    def down(self):
        db = self.db.get_db()
        if self._column_exists(db, "user_test_attempts", "exam_template_id"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts DROP COLUMN exam_template_id"
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
