from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Add is_base, status to exam_instances; answer_order to question_exam_tests."""

    def up(self):
        db = self.db.get_db()
        db.execute_sql("""
            ALTER TABLE exam_instances
            ADD COLUMN IF NOT EXISTS is_base BOOLEAN NOT NULL DEFAULT TRUE
        """)
        db.execute_sql("""
            ALTER TABLE exam_instances
            ADD COLUMN IF NOT EXISTS status SMALLINT NOT NULL DEFAULT 0
        """)
        db.execute_sql("""
            ALTER TABLE question_exam_tests
            ADD COLUMN IF NOT EXISTS answer_order TEXT NULL
        """)
        db.execute_sql("""
            CREATE INDEX IF NOT EXISTS exam_instances_status_idx ON exam_instances(status)
        """)
        db.execute_sql("""
            CREATE INDEX IF NOT EXISTS exam_instances_is_base_idx ON exam_instances(is_base)
        """)

    def down(self):
        db = self.db.get_db()
        db.execute_sql("DROP INDEX IF EXISTS exam_instances_is_base_idx")
        db.execute_sql("DROP INDEX IF EXISTS exam_instances_status_idx")
        db.execute_sql("ALTER TABLE exam_instances DROP COLUMN IF EXISTS is_base")
        db.execute_sql("ALTER TABLE exam_instances DROP COLUMN IF EXISTS status")
        db.execute_sql("ALTER TABLE question_exam_tests DROP COLUMN IF EXISTS answer_order")
