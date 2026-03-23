from abc import ABC, abstractmethod
from src.lib.db.peewee import get_database
import logging

logger = logging.getLogger(__name__)


class BaseSeed(ABC):
    """Base class for database seeds"""

    def __init__(self, name: str):
        """
        Initialize seed

        Args:
            name: Seed name (e.g., "seed_users")
        """
        self.name = name
        self.db = get_database()

    @abstractmethod
    def run(self):
        """Execute seed (populate data)"""
        pass

    def seed(self):
        """Run the seed"""
        try:
            logger.info(f"Running seed: {self.name}")
            self.run()
            logger.info(f"Seed completed: {self.name}")
        except Exception as e:
            logger.error(f"Seed failed: {self.name} - {e}")
            raise

    def cleanup(self):
        """Clean up seed data (optional)"""
        logger.info(f"Cleanup for seed: {self.name}")
