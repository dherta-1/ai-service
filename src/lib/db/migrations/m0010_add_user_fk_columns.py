from src.shared.base.base_migration import BaseMigration


class Migration(BaseMigration):
    """Add user identity FK columns: uploaded_by on documents, created_by on exam_templates/exam_instances, from_user on questions_groups"""

    def up(self):
        db = self.db.get_db()
        db.execute_sql("""
            ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS uploaded_by_id UUID REFERENCES users(id) ON DELETE SET NULL
        """)
        db.execute_sql("""
            CREATE INDEX IF NOT EXISTS documents_uploaded_by_id_idx ON documents(uploaded_by_id)
        """)
        db.execute_sql("""
            ALTER TABLE exam_templates
                ADD COLUMN IF NOT EXISTS created_by_id UUID REFERENCES users(id) ON DELETE SET NULL
        """)
        db.execute_sql("""
            CREATE INDEX IF NOT EXISTS exam_templates_created_by_id_idx ON exam_templates(created_by_id)
        """)
        db.execute_sql("""
            ALTER TABLE exam_instances
                ADD COLUMN IF NOT EXISTS created_by_id UUID REFERENCES users(id) ON DELETE SET NULL
        """)
        db.execute_sql("""
            CREATE INDEX IF NOT EXISTS exam_instances_created_by_id_idx ON exam_instances(created_by_id)
        """)
        db.execute_sql("""
            ALTER TABLE questions_groups
                ADD COLUMN IF NOT EXISTS from_user_id UUID REFERENCES users(id) ON DELETE SET NULL
        """)
        db.execute_sql("""
            CREATE INDEX IF NOT EXISTS questions_groups_from_user_id_idx ON questions_groups(from_user_id)
        """)

    def down(self):
        db = self.db.get_db()
        db.execute_sql("DROP INDEX IF EXISTS documents_uploaded_by_id_idx")
        db.execute_sql("ALTER TABLE documents DROP COLUMN IF EXISTS uploaded_by_id")
        db.execute_sql("DROP INDEX IF EXISTS exam_templates_created_by_id_idx")
        db.execute_sql("ALTER TABLE exam_templates DROP COLUMN IF EXISTS created_by_id")
        db.execute_sql("DROP INDEX IF EXISTS exam_instances_created_by_id_idx")
        db.execute_sql("ALTER TABLE exam_instances DROP COLUMN IF EXISTS created_by_id")
        db.execute_sql("DROP INDEX IF EXISTS questions_groups_from_user_id_idx")
        db.execute_sql("ALTER TABLE questions_groups DROP COLUMN IF EXISTS from_user_id")
