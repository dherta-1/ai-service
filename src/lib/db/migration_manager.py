from peewee import Model, CharField, TextField, DateTimeField
from datetime import datetime
from src.lib.db.peewee import get_database
from src.shared.base.base_migration import BaseMigration
from typing import Type, List, Optional
import logging
import importlib
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class MigrationHistory(Model):
    """Tracks executed migrations"""

    version = CharField(unique=True, primary_key=True)
    description = TextField()
    executed_at = DateTimeField(default=datetime.utcnow)

    class Meta:
        table_name = "migration_history"
        database = None  # Will be set dynamically


class MigrationManager:
    """Manages database migrations"""

    def __init__(self, migrations_dir: str = "src/lib/db/migrations"):
        self.migrations_dir = Path(migrations_dir)
        self.db = get_database()
        self._ensure_migrations_table()

    def _ensure_migrations_table(self):
        """Create migration history table if it doesn't exist"""
        try:
            MigrationHistory._meta.database = self.db.get_db()
            self.db.create_tables([MigrationHistory])
            logger.info("Migration history table ready")
        except Exception as e:
            logger.error(f"Error creating migration history table: {e}")
            raise

    def get_executed_migrations(self) -> List[str]:
        """Get list of executed migration versions"""
        try:
            return [
                m.version
                for m in MigrationHistory.select().order_by(
                    MigrationHistory.executed_at
                )
            ]
        except Exception as e:
            logger.error(f"Error fetching executed migrations: {e}")
            return []

    def get_pending_migrations(self) -> List[str]:
        """Get list of pending migrations"""
        try:
            executed = self.get_executed_migrations()
            all_migrations = self._discover_migrations()
            return [m for m in all_migrations if m not in executed]
        except Exception as e:
            logger.error(f"Error fetching pending migrations: {e}")
            return []

    def _discover_migrations(self) -> List[str]:
        """Discover migration files in migrations directory"""
        migrations = []
        try:
            if not self.migrations_dir.exists():
                logger.warning(f"Migrations directory not found: {self.migrations_dir}")
                return migrations

            for file in sorted(self.migrations_dir.glob("*.py")):
                if file.name.startswith("_"):
                    continue
                version = file.stem
                migrations.append(version)

            logger.info(f"Discovered {len(migrations)} migrations")
            return migrations
        except Exception as e:
            logger.error(f"Error discovering migrations: {e}")
            return migrations

    def _load_migration(self, version: str) -> Optional[BaseMigration]:
        """Load migration class from file"""
        try:
            module_name = f"src.lib.db.migrations.{version}"
            module = importlib.import_module(module_name)

            # Find migration class (first class that inherits from BaseMigration)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseMigration)
                    and attr is not BaseMigration
                ):
                    return attr(version)

            logger.error(f"No migration class found in {version}")
            return None
        except Exception as e:
            logger.error(f"Error loading migration {version}: {e}")
            return None

    def run_pending_migrations(self):
        """Run all pending migrations"""
        pending = self.get_pending_migrations()

        if not pending:
            logger.info("No pending migrations")
            return

        logger.info(f"Running {len(pending)} pending migrations")

        for version in pending:
            migration = self._load_migration(version)
            if migration:
                try:
                    migration.migrate()
                    # Record in history
                    MigrationHistory.create(
                        version=version,
                        description=migration.__class__.__doc__ or version,
                    )
                    logger.info(f"Executed migration: {version}")
                except Exception as e:
                    logger.error(f"Failed to execute migration {version}: {e}")
                    raise

    def rollback_migration(self, version: str):
        """Rollback specific migration"""
        try:
            migration = self._load_migration(version)
            if migration:
                migration.rollback()
                MigrationHistory.delete().where(
                    MigrationHistory.version == version
                ).execute()
                logger.info(f"Rolled back migration: {version}")
            else:
                logger.error(f"Migration not found: {version}")
        except Exception as e:
            logger.error(f"Error rolling back migration {version}: {e}")
            raise

    def rollback_last(self):
        """Rollback last executed migration"""
        try:
            last = (
                MigrationHistory.select()
                .order_by(MigrationHistory.executed_at.desc())
                .first()
            )
            if last:
                self.rollback_migration(last.version)
            else:
                logger.warning("No migrations to rollback")
        except Exception as e:
            logger.error(f"Error rolling back last migration: {e}")
            raise

    def reset(self):
        """Rollback all migrations"""
        try:
            executed = self.get_executed_migrations()
            for version in reversed(executed):
                self.rollback_migration(version)
            logger.info("All migrations rolled back")
        except Exception as e:
            logger.error(f"Error resetting migrations: {e}")
            raise


def get_migration_manager(
    migrations_dir: str = "src/lib/db/migrations",
) -> MigrationManager:
    """Get migration manager instance"""
    return MigrationManager(migrations_dir)
