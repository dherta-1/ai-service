from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Add name_vi to Subject and Topic, add sub_question_order to Question."""

    def up(self):
        """Add Vietnamese name fields and sub_question_order."""
        db_instance = self.db.get_db()

        # Add name_vi to subjects table if column doesn't exist
        db_instance.execute_sql(
            """
            ALTER TABLE subjects
            ADD COLUMN IF NOT EXISTS name_vi VARCHAR(255) NULL
            """
        )

        # Add name_vi to topics table if column doesn't exist
        db_instance.execute_sql(
            """
            ALTER TABLE topics
            ADD COLUMN IF NOT EXISTS name_vi VARCHAR(255) NULL
            """
        )

        # Add sub_question_order to questions table if column doesn't exist
        db_instance.execute_sql(
            """
            ALTER TABLE questions
            ADD COLUMN IF NOT EXISTS sub_question_order INTEGER NULL
            """
        )

    def down(self):
        """Rollback: remove the added columns."""
        db_instance = self.db.get_db()

        # Remove name_vi from subjects table if column exists
        db_instance.execute_sql(
            """
            ALTER TABLE subjects
            DROP COLUMN IF EXISTS name_vi
            """
        )

        # Remove name_vi from topics table if column exists
        db_instance.execute_sql(
            """
            ALTER TABLE topics
            DROP COLUMN IF EXISTS name_vi
            """
        )

        # Remove sub_question_order from questions table if column exists
        db_instance.execute_sql(
            """
            ALTER TABLE questions
            DROP COLUMN IF EXISTS sub_question_order
            """
        )
