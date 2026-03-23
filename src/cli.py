"""
CLI for managing migrations and seeds

Usage:
    python -m src.cli migrate              # Run pending migrations
    python -m src.cli migrate:rollback     # Rollback last migration
    python -m src.cli migrate:status       # Show migration status
    python -m src.cli seed:run             # Run pending seeds
    python -m src.cli seed:run-all [--force]  # Run all seeds
    python -m src.cli seed:cleanup         # Clean up all seeds
"""

import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path
from src.lib.db.migration_manager import get_migration_manager
from src.lib.db.seed_manager import get_seed_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_table(headers, rows):
    """Print formatted table"""
    if not rows:
        print("No data")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Print header
    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(header_line)
    print("-" * len(header_line))

    # Print rows
    for row in rows:
        print(" | ".join(str(c).ljust(w) for c, w in zip(row, widths)))


def create_migration_file(description: str) -> str:
    """Create a new migration file with timestamp prefix"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Convert description to snake_case filename
    filename = description.lower().replace(" ", "_").replace("-", "_")
    filename = "".join(c for c in filename if c.isalnum() or c == "_")

    migration_file = f"{timestamp}_{filename}.py"
    migrations_dir = Path("src/lib/db/migrations")
    migrations_dir.mkdir(parents=True, exist_ok=True)

    filepath = migrations_dir / migration_file

    # Create migration template
    class_name = "".join(word.capitalize() for word in filename.split("_"))
    template = f'''"""
Migration {timestamp}: {description}
"""

from src.shared.base.base_migration import BaseMigration


class Migration{class_name}(BaseMigration):
    """{description}"""

    def up(self):
        """Execute migration (apply changes)"""
        # Bind model to database before executing
        # db_instance = self.db.get_db()
        # Model._meta.database = db_instance
        # db_instance.create_tables([Model])
        pass

    def down(self):
        """Rollback migration (revert changes)"""
        # Bind model to database before executing
        # db_instance = self.db.get_db()
        # Model._meta.database = db_instance
        # db_instance.drop_tables([Model])
        pass
'''

    with open(filepath, "w") as f:
        f.write(template)

    return str(filepath)


def create_seed_file(description: str) -> str:
    """Create a new seed file with timestamp prefix"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Convert description to snake_case filename
    filename = description.lower().replace(" ", "_").replace("-", "_")
    filename = "".join(c for c in filename if c.isalnum() or c == "_")

    seed_file = f"{timestamp}_{filename}.py"
    seeds_dir = Path("src/lib/db/seeds")
    seeds_dir.mkdir(parents=True, exist_ok=True)

    filepath = seeds_dir / seed_file

    # Create seed template
    class_name = "".join(word.capitalize() for word in filename.split("_"))
    template = f'''"""
Seed {timestamp}: {description}
"""

from src.shared.base.base_seed import BaseSeed


class Seed{class_name}(BaseSeed):
    """{description}"""

    def run(self):
        """Execute seed (populate data)"""
        # Bind model to database before executing
        # db_instance = self.db.get_db()
        # Model._meta.database = db_instance
        # Model.create(...)
        pass

    def cleanup(self):
        """Cleanup seed data (optional)"""
        # Bind model to database before executing
        # db_instance = self.db.get_db()
        # Model._meta.database = db_instance
        # Model.delete().where(...).execute()
        pass
'''

    with open(filepath, "w") as f:
        f.write(template)

    return str(filepath)


def migrate_command(args):
    """Handle migration commands"""
    manager = get_migration_manager()

    if args.action == "create":
        if not args.description:
            logger.error("Migration description is required")
            sys.exit(1)
        filepath = create_migration_file(args.description)
        logger.info(f"✓ Migration created: {filepath}")

    elif args.action == "run" or args.action is None:
        logger.info("Running pending migrations...")
        manager.run_pending_migrations()
        logger.info("✓ Migrations completed")

    elif args.action == "status":
        executed = manager.get_executed_migrations()
        pending = manager.get_pending_migrations()

        print("\n=== Migration Status ===")
        print(f"\nExecuted: {len(executed)}")
        if executed:
            for version in executed:
                print(f"  ✓ {version}")

        print(f"\nPending: {len(pending)}")
        if pending:
            for version in pending:
                print(f"  ○ {version}")
        else:
            print("  (none)")

    elif args.action == "rollback":
        logger.info("Rolling back last migration...")
        manager.rollback_last()
        logger.info("✓ Rollback completed")

    elif args.action == "reset":
        if not args.force:
            response = input("This will rollback all migrations. Continue? (yes/no): ")
            if response.lower() != "yes":
                logger.info("Cancelled")
                return

        logger.info("Resetting all migrations...")
        manager.reset()
        logger.info("✓ Reset completed")


def seed_command(args):
    """Handle seed commands"""
    manager = get_seed_manager()

    if args.action == "create":
        if not args.description:
            logger.error("Seed description is required")
            sys.exit(1)
        filepath = create_seed_file(args.description)
        logger.info(f"✓ Seed created: {filepath}")

    elif args.action == "run":
        logger.info("Running pending seeds...")
        manager.run_pending_seeds()
        logger.info("✓ Seeds completed")

    elif args.action == "run-all":
        logger.info("Running all seeds...")
        manager.run_all_seeds(force=args.force)
        logger.info("✓ All seeds completed")

    elif args.action == "cleanup":
        if not args.force:
            response = input("This will delete all seed data. Continue? (yes/no): ")
            if response.lower() != "yes":
                logger.info("Cancelled")
                return

        logger.info("Cleaning up all seeds...")
        manager.cleanup_all()
        logger.info("✓ Cleanup completed")

    elif args.action == "status" or args.action is None:
        executed = manager.get_executed_seeds()
        available = manager.get_available_seeds()
        pending = [s for s in available if s not in executed]

        print("\n=== Seed Status ===")
        print(f"\nAvailable: {len(available)}")
        for name in available:
            status = "✓" if name in executed else "○"
            print(f"  {status} {name}")

        print(f"\nPending: {len(pending)}")
        if not pending:
            print("  (none)")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Database migration and seed CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Migration commands
    migrate_parser = subparsers.add_parser("migrate", help="Migration commands")
    migrate_parser.add_argument(
        "action",
        nargs="?",
        default="run",
        choices=["create", "run", "status", "rollback", "reset"],
        help="Action to perform",
    )
    migrate_parser.add_argument(
        "description",
        nargs="?",
        help="Description for new migration (required for create action)",
    )
    migrate_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force action without confirmation",
    )
    migrate_parser.set_defaults(func=migrate_command)

    # Seed commands
    seed_parser = subparsers.add_parser("seed", help="Seed commands")
    seed_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["create", "run", "run-all", "cleanup", "status"],
        help="Action to perform",
    )
    seed_parser.add_argument(
        "description",
        nargs="?",
        help="Description for new seed (required for create action)",
    )
    seed_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force action without confirmation",
    )
    seed_parser.set_defaults(func=seed_command)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
