from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Make exam_template_id nullable to support one-off exam generation without templates."""

    def up(self):
        db = self.db.get_db()
        db.execute_sql("""
            ALTER TABLE exam_instances
            ALTER COLUMN exam_template_id DROP NOT NULL
        """)
        db.execute_sql("""
            CREATE INDEX IF NOT EXISTS exam_instances_exam_template_id_idx
            ON exam_instances(exam_template_id)
        """)

    def down(self):
        db = self.db.get_db()
        db.execute_sql("""
            DROP INDEX IF EXISTS exam_instances_exam_template_id_idx
        """)
        db.execute_sql("""
            ALTER TABLE exam_instances
            ALTER COLUMN exam_template_id SET NOT NULL
        """)
