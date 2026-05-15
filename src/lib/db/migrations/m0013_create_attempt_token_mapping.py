"""
Migration m0013_create_attempt_token_mapping: Create attempt_token_mappings table
"""

from src.shared.base.base_migration import BaseMigration
from src.entities.attempt_token_mapping import AttemptTokenMapping


class Migration(BaseMigration):
    """Create mapping table for exam attempt tokens"""

    def up(self):
        db_instance = self.db.get_db()
        AttemptTokenMapping._meta.database = db_instance
        db_instance.create_tables([AttemptTokenMapping])

    def down(self):
        db_instance = self.db.get_db()
        AttemptTokenMapping._meta.database = db_instance
        db_instance.drop_tables([AttemptTokenMapping])
