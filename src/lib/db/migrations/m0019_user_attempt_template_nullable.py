from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Make exam_template_id nullable in user_test_attempts for standalone exams"""

    def up(self):
        db = self.db.get_db()
        db.execute_sql(
            "ALTER TABLE user_test_attempts ALTER COLUMN exam_template_id DROP NOT NULL"
        )

    def down(self):
        db = self.db.get_db()
        db.execute_sql(
            "ALTER TABLE user_test_attempts ALTER COLUMN exam_template_id SET NOT NULL"
        )
