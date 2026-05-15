from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Link user_test_attempts to exam_instances"""

    def up(self):
        db = self.db.get_db()

        if not self._column_exists(db, "user_test_attempts", "exam_instance_id"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts ADD COLUMN exam_instance_id UUID NULL"
            )

        if not self._constraint_exists(
            db, "user_test_attempts", "user_test_attempts_exam_instance_id_fkey"
        ):
            db.execute_sql("""
                ALTER TABLE user_test_attempts
                ADD CONSTRAINT user_test_attempts_exam_instance_id_fkey
                FOREIGN KEY (exam_instance_id) REFERENCES exam_instances (id)
                """)

        if not self._index_exists(
            db, "user_test_attempts", "idx_user_test_attempts_exam_instance_id"
        ):
            db.execute_sql(
                "CREATE INDEX idx_user_test_attempts_exam_instance_id ON user_test_attempts (exam_instance_id)"
            )

    def down(self):
        db = self.db.get_db()

        if self._index_exists(
            db, "user_test_attempts", "idx_user_test_attempts_exam_instance_id"
        ):
            db.execute_sql("DROP INDEX idx_user_test_attempts_exam_instance_id")

        if self._constraint_exists(
            db, "user_test_attempts", "user_test_attempts_exam_instance_id_fkey"
        ):
            db.execute_sql(
                "ALTER TABLE user_test_attempts DROP CONSTRAINT user_test_attempts_exam_instance_id_fkey"
            )

        if self._column_exists(db, "user_test_attempts", "exam_instance_id"):
            db.execute_sql(
                "ALTER TABLE user_test_attempts DROP COLUMN exam_instance_id"
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

    @staticmethod
    def _constraint_exists(db, table: str, constraint: str) -> bool:
        result = db.execute_sql(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = %s AND constraint_name = %s
            """,
            (table, constraint),
        ).fetchone()
        return result is not None

    @staticmethod
    def _index_exists(db, table: str, index: str) -> bool:
        result = db.execute_sql(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = %s AND indexname = %s
            """,
            (table, index),
        ).fetchone()
        return result is not None
