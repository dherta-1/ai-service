"""
Seed: Sample project metadata

This seed populates the project_metadata table with sample data for testing.
"""

from src.shared.base.base_seed import BaseSeed
from src.entities.project_metadata import ProjectMetadata


class SampleProjectsMetadata(BaseSeed):
    """Seed sample project metadata"""

    def run(self):
        """Insert sample data"""
        # Bind model to database before querying
        db_instance = self.db.get_db()
        ProjectMetadata._meta.database = db_instance

        # Clear existing data (optional)
        # ProjectMetadata.delete().execute()

        # Insert sample projects
        projects = [
            {
                "name": "FastAPI Minimal Template",
                "description": "A minimal FastAPI template with DI, Redis, Peewee, Kafka, and gRPC",
                "version": "0.1.0",
            },
            {
                "name": "Project Alpha",
                "description": "An example project for demonstration",
                "version": "1.0.0",
            },
            {
                "name": "Project Beta",
                "description": "Another example project",
                "version": "2.1.3",
            },
        ]

        created_count = 0
        for project_data in projects:
            # Check if project already exists
            if (
                not ProjectMetadata.select()
                .where(ProjectMetadata.name == project_data["name"])
                .exists()
            ):
                ProjectMetadata.create(**project_data)
                created_count += 1

        self.logger = __import__("logging").getLogger(__name__)
        self.logger.info(f"Created {created_count} new projects")

    def cleanup(self):
        """Delete sample data"""
        # Bind model to database before querying
        db_instance = self.db.get_db()
        ProjectMetadata._meta.database = db_instance

        ProjectMetadata.delete().where(
            ProjectMetadata.name.in_(
                [
                    "FastAPI Minimal Template",
                    "Project Alpha",
                    "Project Beta",
                ]
            )
        ).execute()
