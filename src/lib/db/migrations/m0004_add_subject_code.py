"""
Migration m0004: Add subject_code to Topic table to link topics with their parent subject.
"""

from src.shared.base.base_migration import BaseMigration


class MigrationAddSubjectCode(BaseMigration):
    """Add subject_code to topics table to establish subject-topic relationship."""

    def up(self):
        """Add subject_code column to topics table."""
        db_instance = self.db.get_db()

        # Add subject_code to topics table if column doesn't exist
        db_instance.execute_sql(
            """
            ALTER TABLE topics
            ADD COLUMN IF NOT EXISTS subject_code VARCHAR(50) NULL
            """
        )

        # Create index on subject_code for efficient querying
        db_instance.execute_sql(
            """
            CREATE INDEX IF NOT EXISTS topics_subject_code_idx ON topics(subject_code)
            """
        )

    def down(self):
        """Rollback: remove subject_code column."""
        db_instance = self.db.get_db()

        # Drop the index if it exists
        db_instance.execute_sql(
            """
            DROP INDEX IF EXISTS topics_subject_code_idx
            """
        )

        # Remove subject_code from topics table if column exists
        db_instance.execute_sql(
            """
            ALTER TABLE topics
            DROP COLUMN IF EXISTS subject_code
            """
        )
