# FastAPI Minimal Template

A production-ready FastAPI template with Dependency Injection, Redis caching, Peewee ORM, Kafka event streaming, and gRPC support.

## Features

- **FastAPI**: Modern async web framework with automatic API documentation
- **gRPC**: High-performance RPC framework with protocol buffers
- **Dependency Injection**: Custom DI container for managing dependencies
- **Peewee ORM**: Lightweight but powerful object-relational mapper
  - BaseEntity with UUID primary key
  - Automatic `created_at` and `updated_at` timestamps
- **Redis Caching**: Built-in cache client for performance optimization
- **Kafka Integration**: Producer and consumer implementations for event streaming
- **Docker Support**: Dockerfile and docker-compose for easy deployment
- **Structured Code**: Clean architecture with entities, repositories, services, and DTOs

## Project Structure

```
├── src/
│   ├── app.py                    # FastAPI application factory
│   ├── settings.py               # Configuration management
│   ├── worker.py                 # Kafka consumer worker
│   ├── dtos/                     # Data Transfer Objects
│   │   └── project_metadata/
│   │       ├── req.py           # Request DTOs
│   │       └── res.py           # Response DTOs
│   ├── entities/                 # Database models
│   │   └── project_metadata.py
│   ├── grpc/                     # gRPC services
│   │   ├── project_metadata_servicer.py
│   │   └── client.py            # gRPC client example
│   ├── grpc_generated/           # Generated gRPC code
│   │   └── project_metadata_pb2.py
│   ├── lib/
│   │   ├── cachedb/             # Cache implementations
│   │   │   └── redis.py
│   │   ├── db/                  # Database management
│   │   │   ├── peewee.py
│   │   │   ├── migration_manager.py
│   │   │   ├── seed_manager.py
│   │   │   ├── migrations/      # Migration files
│   │   │   │   └── 001_create_project_metadata.py
│   │   │   └── seeds/           # Seed files
│   │   │       └── seed_sample_projects.py
│   │   ├── di/                  # Dependency Injection
│   │   │   └── container.py
│   │   ├── event_bus/           # Event streaming
│   │   │   ├── base/
│   │   │   │   ├── base_consumer.py
│   │   │   │   └── base_producer.py
│   │   │   └── kafka/
│   │   │       ├── consumer.py
│   │   │       └── producer.py
│   │   ├── grpc_server.py        # gRPC server manager
│   ├── cli.py                    # CLI for migrations and seeds
│   ├── proto/                    # Protocol buffer definitions
│   │   ├── common.proto
│   │   └── project_metadata.proto
│   ├── repos/                    # Repository layer
│   │   └── project_metadata_repo.py
│   ├── routes/                   # API routes
│   │   └── system_route.py
│   ├── services/                 # Business logic
│   │   └── project_metadata_service.py
│   └── shared/                   # Shared utilities
│       ├── base/
│       │   ├── base_entity.py
│       │   ├── base_migration.py
│       │   ├── base_repo.py
│       │   ├── base_seed.py
│       │   └── base_service.py
│       ├── constants/
│       ├── logger/
│       └── utils/
├── scripts/
│   └── generate_grpc.sh          # Generate gRPC code from proto
├── main.py                       # API server entry point
├── Dockerfile                    # Docker build configuration
├── docker-compose.yml            # Multi-container setup
├── Makefile                      # Development commands
├── pyproject.toml               # Project dependencies
└── README.md                     # This file
```

## Installation

### Prerequisites

- Python 3.12+
- Docker and Docker Compose (optional)

### Local Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd fastapi-minimal-template
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/Scripts/activate  # On Windows
   # or
   source venv/bin/activate      # On Unix/macOS
   ```

3. **Install dependencies**
   ```bash
   pip install -e .
   # For development:
   pip install -e ".[dev]"
   ```

4. **Create .env file**
   ```bash
   cp .env.example .env
   ```

5. **Run the application**
   ```bash
   python main.py
   ```

The API will be available at `http://localhost:8000`

#### API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Docker Setup

1. **Build and start services**
   ```bash
   docker-compose up -d
   ```

2. **View logs**
   ```bash
   docker-compose logs -f api
   ```

3. **Stop services**
   ```bash
   docker-compose down
   ```

## Usage

### Creating an Entity

Define a new entity extending `BaseEntity`:

```python
from src.shared.base.base_entity import BaseEntity
from peewee import CharField

class User(BaseEntity):
    email = CharField(unique=True)
    name = CharField()

    class Meta:
        table_name = "users"
```

### Creating a Repository

Extend `BaseRepo` with custom queries:

```python
from src.shared.base.base_repo import BaseRepo
from src.entities.user import User

class UserRepo(BaseRepo[User]):
    def __init__(self):
        super().__init__(User)

    def get_by_email(self, email: str) -> User | None:
        return self.filter_one(email=email)
```

### Creating a Service

Extend `BaseService` for business logic:

```python
from src.shared.base.base_service import BaseService
from src.repos.user_repo import UserRepo

class UserService(BaseService[User]):
    def __init__(self, repo: UserRepo = None):
        if repo is None:
            repo = UserRepo()
        super().__init__(repo)
```

### Creating API Routes

```python
from fastapi import APIRouter, Depends

router = APIRouter()

def get_user_service() -> UserService:
    return UserService()

@router.get("/users/{user_id}")
async def get_user(user_id: UUID, service: UserService = Depends(get_user_service)):
    user = service.get_by_id(user_id)
    return user
```

### Using Redis Cache

```python
from src.lib.cachedb.redis import get_cache_client

cache = get_cache_client()

# Get value
value = cache.get("my_key")

# Set value
cache.set("my_key", {"data": "value"}, ttl=3600)

# Delete value
cache.delete("my_key")

# Check existence
if cache.exists("my_key"):
    print("Key exists")
```

### Using Kafka Producer

The application uses [Confluent Kafka](https://docs.confluent.io/kafka-clients/python/current/overview.html) for producer/consumer implementations.

```python
from src.lib.event_bus.kafka.producer import KafkaProducerImpl

producer = KafkaProducerImpl(topic="my-topic")

# Send message
success = producer.send(
    key="user_id",
    value={"action": "created", "user_id": "123"}
)

# Flush pending messages
producer.flush(timeout=30)
producer.close()
```

### Using Kafka Consumer

```python
from src.lib.event_bus.kafka.consumer import KafkaConsumerImpl

def handle_event(key, value):
    print(f"Received: {key} -> {value}")

consumer = KafkaConsumerImpl(
    topics=["my-topic"],
    handler=handle_event
)

consumer.start()  # Runs in background thread
```

## gRPC Integration

The application includes a gRPC server that runs alongside the REST API.

### Generating gRPC Code

First, generate Python code from proto files:

```bash
# Using make (recommended)
make grpc-generate

# Or manually with protoc
python -m grpc_tools.protoc \
    -Isrc/proto \
    --python_out=src/grpc_generated \
    --grpc_python_out=src/grpc_generated \
    src/proto/project_metadata.proto
```

### Proto Files

Proto definitions are in `src/proto/`:

```protobuf
// src/proto/project_metadata.proto
service ProjectMetadataService {
    rpc CreateProject(ProjectMetadataRequest) returns (ProjectMetadataResponse);
    rpc GetProject(ProjectMetadataIdRequest) returns (ProjectMetadataResponse);
    rpc ListProjects(common.Empty) returns (ProjectMetadataListResponse);
    rpc UpdateProject(ProjectMetadataUpdateRequest) returns (ProjectMetadataResponse);
    rpc DeleteProject(ProjectMetadataIdRequest) returns (common.Empty);
}
```

### gRPC Server

The gRPC server starts automatically with the FastAPI application on port `50051` (configurable via `GRPC_PORT`).

### Using gRPC Client

```python
import grpc
from src.grpc_generated.project_metadata_pb2_grpc import ProjectMetadataServiceStub
from src.grpc_generated.project_metadata_pb2 import ProjectMetadataRequest

channel = grpc.aio.insecure_channel('localhost:50051')
stub = ProjectMetadataServiceStub(channel)

response = stub.CreateProject(ProjectMetadataRequest(
    name="Test Project",
    description="A test project",
    version="1.0.0"
))

print(f"Created project: {response.id}")
```

### Creating Custom gRPC Services

1. Define your service in `src/proto/your_service.proto`
2. Run `make grpc-generate` to generate Python code
3. Implement servicer in `src/grpc/your_service_servicer.py`
4. Register in `src/lib/grpc_server.py`

## Dependency Injection

The DI container manages singletons and factories:

```python
from src.lib.di.container import get_di_container

container = get_di_container()

# Register singleton
container.register_singleton("db", database_instance)

# Register factory
container.register_factory("service", lambda: UserService())

# Get instance
db = container.get("db")
```

## Configuration

Settings are loaded from environment variables and `.env` file:

```python
from src.settings import get_settings

settings = get_settings()
print(settings.app_name)
print(settings.database_url)
```

Available settings:
- `APP_NAME`: Application name
- `DEBUG`: Debug mode
- `HOST`: Server host
- `PORT`: Server port (HTTP)
- `GRPC_PORT`: gRPC server port
- `DATABASE_URL`: Database connection string
- `REDIS_URL`: Redis connection string
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka brokers

## API Endpoints

### Projects (Sample)

- `POST /api/system/projects` - Create project
- `GET /api/system/projects` - List projects
- `GET /api/system/projects/{project_id}` - Get project
- `PUT /api/system/projects/{project_id}` - Update project
- `DELETE /api/system/projects/{project_id}` - Delete project

- `GET /health` - Health check
- `GET /` - Welcome endpoint

## Development

### Available Commands

Use the `Makefile` for common development tasks:

```bash
# Install dependencies
make install
make dev  # with dev tools

# Code quality
make format    # Format with black
make lint      # Run linters
make test      # Run tests

# gRPC
make grpc-generate  # Generate gRPC code from proto

# Docker
make docker-up      # Start services
make docker-down    # Stop services
make docker-logs    # View logs

# Running
make run            # Run API server
make run-worker     # Run Kafka worker

# Cleanup
make clean          # Remove cache and temp files
```

### Running Tests

```bash
pytest tests/
```

### Code Quality

```bash
# Format code
black src/

# Lint
flake8 src/

# Type checking
mypy src/
```

### Database Migrations

Migrations are managed with a custom migration system that tracks executed migrations.

#### Running Migrations

Migrations run automatically on application startup. To run manual migrations:

```bash
# Run pending migrations
make migrate

# Check migration status
make migrate-status

# Rollback last migration
make migrate-rollback

# Reset all migrations
make migrate-reset
```

Or using the CLI directly:

```bash
python -m src.cli migrate run
python -m src.cli migrate status
python -m src.cli migrate rollback
python -m src.cli migrate reset --force
```

#### Creating a Migration

Create a new migration file in `src/lib/db/migrations/`:

```python
# src/lib/db/migrations/002_add_user_table.py
from src.shared.base.base_migration import BaseMigration
from src.entities.user import User

class Migration002AddUserTable(BaseMigration):
    """Add user table to database"""

    def up(self):
        """Create table"""
        self.db.create_tables([User])

    def down(self):
        """Drop table"""
        self.db.drop_tables([User])
```

Migration files are discovered and executed in alphabetical order.

### Database Seeds

Seeds populate the database with initial data and run after migrations.

#### Running Seeds

```bash
# Run pending seeds only
make seed-run

# Run all seeds (even if already executed)
make seed-run-all

# Check seed status
make seed-status

# Clean up all seed data
make seed-cleanup
```

Or using the CLI:

```bash
python -m src.cli seed run
python -m src.cli seed run-all --force
python -m src.cli seed status
python -m src.cli seed cleanup --force
```

#### Creating a Seed

Create a new seed file in `src/lib/db/seeds/`:

```python
# src/lib/db/seeds/seed_users.py
from src.shared.base.base_seed import BaseSeed
from src.entities.user import User

class SeedUsers(BaseSeed):
    """Seed initial users"""

    def run(self):
        """Insert data"""
        User.create(
            email="admin@example.com",
            name="Admin User"
        )

    def cleanup(self):
        """Delete seed data"""
        User.delete().where(User.email == "admin@example.com").execute()
```

#### Auto-running Seeds on Startup

Enable seeds on application startup by setting the environment variable:

```bash
RUN_SEEDS=true
```

## Troubleshooting

### Database Connection Error

Ensure `DATABASE_URL` is set correctly:
```bash
# For SQLite (default)
DATABASE_URL=sqlite:///./db.sqlite

# For PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

### Redis Connection Error

Ensure Redis is running:
```bash
redis-cli ping  # Should return PONG
```

### Kafka Connection Error

Ensure Kafka is running and accessible:
```bash
docker-compose logs kafka
```

## Logging

Logging is configured automatically. View logs:

```bash
# Docker
docker-compose logs -f api

# Local
tail -f app.log
```

## Production Deployment

1. Update `.env` with production settings
2. Use PostgreSQL instead of SQLite
3. Set `DEBUG=false`
4. Use a production ASGI server:
   ```bash
   gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.app:app
   ```

## Contributing

1. Create a feature branch
2. Follow code style (black, flake8)
3. Add tests for new features
4. Submit pull request

## License

MIT
