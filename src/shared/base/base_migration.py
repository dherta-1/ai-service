from abc import ABC, abstractmethod
from src.lib.db.peewee import get_database
import logging

logger = logging.getLogger(__name__)


class BaseMigration(ABC):
    """Base class for database migrations"""

    def __init__(self, version: str):
        """
        Initialize migration

        Args:
            version: Migration version (e.g., "001_create_users_table")
        """
        self.version = version
        self.db = get_database()

    @abstractmethod
    def up(self):
        """Execute migration (apply changes)"""
        pass

    @abstractmethod
    def down(self):
        """Rollback migration (revert changes)"""
        pass

    def migrate(self):
        """Run the migration"""
        try:
            logger.info(f"Running migration: {self.version}")
            self.up()
            logger.info(f"Migration completed: {self.version}")
        except Exception as e:
            logger.error(f"Migration failed: {self.version} - {e}")
            raise

    def rollback(self):
        """Rollback the migration"""
        try:
            logger.info(f"Rolling back migration: {self.version}")
            self.down()
            logger.info(f"Rollback completed: {self.version}")
        except Exception as e:
            logger.error(f"Rollback failed: {self.version} - {e}")
            raise
