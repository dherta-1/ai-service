from peewee import Model, CharField, DateTimeField
from datetime import datetime
from src.lib.db.peewee import get_database
from src.shared.base.base_seed import BaseSeed
from typing import List, Optional
import logging
import importlib
from pathlib import Path

logger = logging.getLogger(__name__)


class SeedHistory(Model):
    """Tracks executed seeds"""

    name = CharField(unique=True, primary_key=True)
    executed_at = DateTimeField(default=datetime.utcnow)

    class Meta:
        table_name = "seed_history"
        database = None  # Will be set dynamically


class SeedManager:
    """Manages database seeds"""

    def __init__(self, seeds_dir: str = "src/lib/db/seeds"):
        self.seeds_dir = Path(seeds_dir)
        self.db = get_database()
        self._ensure_seed_history_table()

    def _ensure_seed_history_table(self):
        """Create seed history table if it doesn't exist"""
        try:
            SeedHistory._meta.database = self.db.get_db()
            self.db.create_tables([SeedHistory])
            logger.info("Seed history table ready")
        except Exception as e:
            logger.error(f"Error creating seed history table: {e}")
            raise

    def get_executed_seeds(self) -> List[str]:
        """Get list of executed seeds"""
        try:
            return [
                s.name for s in SeedHistory.select().order_by(SeedHistory.executed_at)
            ]
        except Exception as e:
            logger.error(f"Error fetching executed seeds: {e}")
            return []

    def get_available_seeds(self) -> List[str]:
        """Get list of available seeds"""
        seeds = []
        try:
            if not self.seeds_dir.exists():
                logger.warning(f"Seeds directory not found: {self.seeds_dir}")
                return seeds

            for file in sorted(self.seeds_dir.glob("*.py")):
                if file.name.startswith("_"):
                    continue
                name = file.stem
                seeds.append(name)

            logger.info(f"Discovered {len(seeds)} seeds")
            return seeds
        except Exception as e:
            logger.error(f"Error discovering seeds: {e}")
            return seeds

    def _load_seed(self, name: str) -> Optional[BaseSeed]:
        """Load seed class from file"""
        try:
            module_name = f"src.lib.db.seeds.{name}"
            module = importlib.import_module(module_name)

            # Find seed class (first class that inherits from BaseSeed)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseSeed)
                    and attr is not BaseSeed
                ):
                    return attr(name)

            logger.error(f"No seed class found in {name}")
            return None
        except Exception as e:
            logger.error(f"Error loading seed {name}: {e}")
            return None

    def run_seed(self, name: str, force: bool = False):
        """Run specific seed"""
        try:
            executed = self.get_executed_seeds()

            if name in executed and not force:
                logger.info(f"Seed already executed: {name}")
                return

            seed = self._load_seed(name)
            if seed:
                seed.seed()
                # Record in history
                if name in executed:
                    # Update timestamp if re-running
                    SeedHistory.update(executed_at=datetime.utcnow()).where(
                        SeedHistory.name == name
                    ).execute()
                else:
                    SeedHistory.create(name=name)

                logger.info(f"Executed seed: {name}")
            else:
                logger.error(f"Seed not found: {name}")
        except Exception as e:
            logger.error(f"Error running seed {name}: {e}")
            raise

    def run_all_seeds(self, force: bool = False):
        """Run all available seeds"""
        available = self.get_available_seeds()

        if not available:
            logger.info("No seeds available")
            return

        logger.info(f"Running {len(available)} seeds")

        for name in available:
            self.run_seed(name, force=force)

    def run_pending_seeds(self):
        """Run only pending (not yet executed) seeds"""
        executed = self.get_executed_seeds()
        available = self.get_available_seeds()
        pending = [s for s in available if s not in executed]

        if not pending:
            logger.info("No pending seeds")
            return

        logger.info(f"Running {len(pending)} pending seeds")

        for name in pending:
            self.run_seed(name)

    def cleanup_seed(self, name: str):
        """Clean up seed data"""
        try:
            seed = self._load_seed(name)
            if seed:
                seed.cleanup()
                logger.info(f"Cleaned up seed: {name}")
            else:
                logger.error(f"Seed not found: {name}")
        except Exception as e:
            logger.error(f"Error cleaning up seed {name}: {e}")
            raise

    def cleanup_all(self):
        """Clean up all seeds"""
        executed = self.get_executed_seeds()

        for name in reversed(executed):
            try:
                self.cleanup_seed(name)
            except Exception as e:
                logger.error(f"Error cleaning up seed {name}: {e}")

        logger.info("All seeds cleaned up")


def get_seed_manager(seeds_dir: str = "src/lib/db/seeds") -> SeedManager:
    """Get seed manager instance"""
    return SeedManager(seeds_dir)
