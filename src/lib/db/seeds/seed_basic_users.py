import bcrypt
from src.shared.base.base_seed import BaseSeed
from src.entities.user import User
from src.shared.constants.user import Role
import logging

logger = logging.getLogger(__name__)


class SeedBasicUsers(BaseSeed):
    """Seed database with basic users for all roles"""

    def __init__(self, name: str = "seed_basic_users"):
        super().__init__(name)

    def _hash_password(self, plain: str) -> str:
        """Hash password using bcrypt"""
        plain_bytes = plain.encode('utf-8')[:72]
        return bcrypt.hashpw(plain_bytes, bcrypt.gensalt(rounds=12)).decode('utf-8')

    def run(self):
        """Create basic users for testing"""
        db_instance = self.db.get_db()
        User._meta.database = db_instance

        # Define seed users
        users_data = [
            {
                "email": "admin@example.com",
                "name": "Admin User",
                "password": "AdminPassword123",
                "role": Role.admin.value,
                "is_email_verified": True,
            },
            {
                "email": "user@example.com",
                "name": "Regular User",
                "password": "UserPassword123",
                "role": Role.user.value,
                "is_email_verified": True,
            },
            {
                "email": "teacher@example.com",
                "name": "Teacher User",
                "password": "TeacherPassword123",
                "role": Role.user.value,
                "is_email_verified": True,
            },
        ]

        created_count = 0
        for user_data in users_data:
            try:
                # Check if user already exists
                existing = User.get_or_none(User.email == user_data["email"])
                if existing:
                    logger.info(f"User already exists: {user_data['email']}")
                    continue

                # Hash password and create user
                password_hash = self._hash_password(user_data.pop("password"))
                user = User.create(
                    password_hash=password_hash,
                    **user_data
                )
                created_count += 1
                logger.info(f"Created user: {user.email} ({user.role})")
            except Exception as e:
                logger.error(f"Error creating user {user_data.get('email')}: {e}")
                raise

        logger.info(f"Seed complete: created {created_count} users")

    def cleanup(self):
        """Remove seed users"""
        db_instance = self.db.get_db()
        User._meta.database = db_instance

        seed_emails = [
            "admin@example.com",
            "user@example.com",
            "teacher@example.com",
        ]

        deleted_count = 0
        for email in seed_emails:
            try:
                User.delete().where(User.email == email).execute()
                deleted_count += 1
                logger.info(f"Deleted user: {email}")
            except Exception as e:
                logger.error(f"Error deleting user {email}: {e}")

        logger.info(f"Cleanup complete: deleted {deleted_count} users")
