"""
Migration m0002_add_overlap_content: Add overlap_content field to Page table
"""

from src.lib.db.peewee import get_database
from src.shared.base.base_migration import BaseMigration
from src.entities.page import Page


class MigrationAddOverlapContent(BaseMigration):
    """Add overlap_content field to Page table for question extraction"""

    def up(self):
        db_instance = self.db.get_db()
        Page._meta.database = db_instance

        # Add overlap_content column if it doesn't exist
        if not db_instance.get_columns("page"):
            return

        columns = {col.name for col in db_instance.get_columns("page")}
        if "overlap_content" not in columns:
            db_instance.execute_sql(
                "ALTER TABLE page ADD COLUMN overlap_content TEXT NULL;"
            )

    def down(self):
        db_instance = self.db.get_db()
        Page._meta.database = db_instance

        # Remove overlap_content column if it exists
        columns = {col.name for col in db_instance.get_columns("page")}
        if "overlap_content" in columns:
            db_instance.execute_sql(
                "ALTER TABLE page DROP COLUMN overlap_content;"
            )
