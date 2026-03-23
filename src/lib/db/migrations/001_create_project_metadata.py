"""
Migration 001: Create project_metadata table

This migration creates the initial project_metadata table with UUID primary key
and automatic timestamps.
"""

from src.shared.base.base_migration import BaseMigration
from src.entities.project_metadata import ProjectMetadata


class Migration001CreateProjectMetadata(BaseMigration):
    """Create project_metadata table"""

    def up(self):
        """Create table"""
        # Bind model to database before creating table
        db_instance = self.db.get_db()
        ProjectMetadata._meta.database = db_instance
        db_instance.create_tables([ProjectMetadata])

    def down(self):
        """Drop table"""
        # Bind model to database before dropping table
        db_instance = self.db.get_db()
        ProjectMetadata._meta.database = db_instance
        db_instance.drop_tables([ProjectMetadata])
