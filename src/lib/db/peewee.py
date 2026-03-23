from peewee import SqliteDatabase, PostgresqlDatabase, MySQLDatabase
from src.settings import get_settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connection and initialization"""

    _instance: Optional[object] = None

    def __init__(self):
        self.db = None
        self._initialize_db()

    def _initialize_db(self):
        """Initialize database connection based on settings"""
        settings = get_settings()
        database_url = settings.database_url

        try:
            if database_url.startswith("sqlite"):
                # Parse SQLite URL: sqlite:///path/to/db.sqlite
                db_path = database_url.replace("sqlite:///", "")
                self.db = SqliteDatabase(db_path)
                logger.info(f"Connected to SQLite database: {db_path}")

            elif database_url.startswith("postgres"):
                # Parse PostgreSQL URL
                self.db = PostgresqlDatabase(database_url)
                logger.info(f"Connected to PostgreSQL database")

            elif database_url.startswith("mysql"):
                # Parse MySQL URL
                self.db = MySQLDatabase(database_url)
                logger.info(f"Connected to MySQL database")

            else:
                raise ValueError(f"Unsupported database URL: {database_url}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    @classmethod
    def get_instance(cls) -> object:
        """Get or create singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_db(self):
        """Get database instance"""
        return self.db

    def close(self):
        """Close database connection"""
        if self.db:
            self.db.close()
            logger.info("Database connection closed")

    def create_tables(self, models: list):
        """Create tables for given models"""
        if self.db:
            self.db.create_tables(models)
            logger.info(f"Created tables for {len(models)} models")

    def drop_tables(self, models: list):
        """Drop tables for given models"""
        if self.db:
            self.db.drop_tables(models)
            logger.info(f"Dropped tables for {len(models)} models")


def get_database() -> DatabaseManager:
    """Get database manager instance"""
    return DatabaseManager.get_instance()
