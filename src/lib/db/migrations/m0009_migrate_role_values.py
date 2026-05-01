from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Migrate role values: remap student/teacher → user, keep admin"""

    def up(self):
        db = self.db.get_db()
        db.execute_sql("""
            UPDATE users SET role = 'user' WHERE role IN ('student', 'teacher')
        """)

    def down(self):
        db = self.db.get_db()
        db.execute_sql("""
            UPDATE users SET role = 'student' WHERE role = 'user'
        """)
