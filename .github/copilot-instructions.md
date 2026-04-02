# AI Service Codebase Instructions

This document provides guidance for developing features and maintaining the ai-service microservice, which handles document processing, project metadata management, and AI-powered operations.

---

## 📋 Quick Start

### Prerequisites & Setup

- **Python 3.12+** with `uv` package manager
- **Docker & Docker Compose** for local infrastructure (PostgreSQL, Redis, Kafka)
- **.env file**: Copy `.env.example` and configure services (database, LLM, OCR, S3 credentials)

### Common Commands

```bash
# Install dependencies
make install
make dev  # includes testing tools

# Database operations
make migrate          # Run pending migrations
make migrate-create   # Create new migration
make seed-run         # Run seeds
make seed-create      # Create new seed

# Code quality
make test             # Run pytest with coverage
make lint             # flake8 + mypy
make format           # black formatting

# gRPC
make grpc-generate    # Generate code from .proto files

# Running services
make run              # Start FastAPI server (port 8000)
make run-worker       # Start Kafka consumer worker
make docker-up        # Start Docker Compose services
```

---

## 🏗️ Architecture Overview

The ai-service follows **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────┐
│  Interface Layer (gRPC, REST API, CLI)          │
├─────────────────────────────────────────────────┤
│  Service Layer (Business Logic)                 │
├─────────────────────────────────────────────────┤
│  Repository Layer (Data Access)                 │
├─────────────────────────────────────────────────┤
│  Entity Layer (Domain Models)                   │
├─────────────────────────────────────────────────┤
│  Infrastructure Layer (External Services)       │
├─────────────────────────────────────────────────┤
│  Shared: DI Container, Event Bus, Settings      │
└─────────────────────────────────────────────────┘
```

### Core Technologies

| Component         | Technology              | Purpose                                          |
| ----------------- | ----------------------- | ------------------------------------------------ |
| **Web Framework** | FastAPI                 | Async REST API with auto-docs                    |
| **RPC Framework** | gRPC + Protocol Buffers | High-performance inter-service communication     |
| **ORM**           | Peewee                  | Lightweight database abstraction with migrations |
| **Cache**         | Redis                   | Session/query caching, event delivery            |
| **Event Bus**     | Kafka                   | Async event streaming for document processing    |
| **AI/LLM**        | Gemini, OpenAI, Ollama  | Text processing and analysis                     |
| **OCR**           | PaddleOCR               | Document image text extraction                   |
| **Storage**       | S3/Boto3                | File persistence                                 |
| **DI**            | Custom DIContainer      | Lightweight dependency injection                 |

---

## 📁 Directory Structure & Responsibilities

```
src/
├── settings.py                 # Pydantic config (env vars)
├── container.py               # Custom DI container & registration
├── app.py                     # FastAPI app factory & setup
├── cli.py                     # CLI commands (migrations, seeds)
├── worker.py                  # Kafka consumer entry point
├── main.py                    # Application entry point
│
├── entities/                  # Domain models (Peewee)
│   └── project_metadata.py    # Example entity with UUID & timestamps
│
├── dtos/                      # Data Transfer Objects (Pydantic)
│   └── project_metadata/
│       ├── req.py             # Request models (input validation)
│       └── res.py             # Response models (output schemas)
│
├── repos/                     # Repository layer (data access)
│   └── project_metadata_repo.py  # Abstracts entity queries
│
├── services/                  # Service layer (business logic)
│   └── project_metadata_service.py  # Orchestrates repos + external services
│
├── routes/                    # API route handlers
│   └── system_route.py        # Health check, status endpoints
│
├── grpc/                      # gRPC service implementations
│   ├── project_metadata_servicer.py  # Implements proto services
│   └── client.py              # gRPC client examples
│
├── grpc_generated/            # Auto-generated from .proto files
│   ├── common_pb2.py
│   └── project_metadata_pb2_grpc.py
│
├── proto/                     # Protocol buffer definitions
│   ├── common.proto
│   └── project_metadata.proto
│
├── handlers/                  # Event handlers
│   ├── event_dispatcher.py    # Router for Kafka events
│   └── project_events.py      # Domain event handlers
│
├── lib/                       # Infrastructure & utilities
│   ├── cachedb/
│   │   ├── base.py            # Abstract cache interface
│   │   └── redis.py           # Redis implementation
│   │
│   ├── db/
│   │   ├── peewee.py          # Database connection manager
│   │   ├── migration_manager.py
│   │   ├── seed_manager.py
│   │   ├── migrations/        # Migration scripts (001_*.py)
│   │   └── seeds/             # Seed data scripts
│   │
│   ├── event_bus/
│   │   ├── base/
│   │   │   ├── base_consumer.py    # Abstract consumer
│   │   │   └── base_producer.py    # Abstract producer
│   │   └── kafka/
│   │       ├── consumer.py         # Kafka consumer impl
│   │       └── producer.py         # Kafka producer impl
│   │
│   ├── llm/
│   │   ├── base.py                 # Abstract LLM interface
│   │   ├── gemini.py               # Google Gemini adapter
│   │   ├── openai.py               # OpenAI adapter
│   │   ├── ollama.py               # Ollama adapter
│   │   └── dtos.py                 # LLM request/response models
│   │
│   ├── ocr/
│   │   ├── base.py                 # Abstract OCR interface
│   │   ├── paddleocrvl.py          # PaddleOCR visual layout adapter
│   │   └── dtos.py                 # OCR request/response models
│   │
│   ├── grpc_server.py              # gRPC server manager
│   └── s3_client.py                # S3 storage client
│
├── shared/                    # Shared utilities & base classes
│   ├── base/
│   │   ├── base_entity.py          # Entity with UUID, timestamps
│   │   ├── base_repo.py            # Common CRUD operations
│   │   ├── base_service.py         # Common service patterns
│   │   ├── base_migration.py       # Migration base
│   │   ├── base_seed.py            # Seed base
│   │   ├── base_handler.py         # Event handler base
│   │   └── base_trigger.py         # Database trigger base
│   │
│   ├── constants/                  # App-wide constants
│   ├── logger/                     # Logging configuration
│   ├── response/
│   │   ├── exception_handler.py    # Error handling middleware
│   │   └── response_models.py      # Standard response wrapper
│   └── utils/                      # Utility functions
```

---

## 🔄 Implementation Patterns

### 1️⃣ Creating a New Domain Entity

**Step 1: Define Entity** (`src/entities/my_entity.py`)

```python
from src.shared.base.base_entity import BaseEntity
from peewee import CharField, TextField

class MyEntity(BaseEntity):
    """Your domain entity"""
    name = CharField()
    description = TextField(null=True)

    class Meta:
        table_name = "my_entities"
```

**Step 2: Create Migration** (`make migrate-create`)

- Migration file auto-created at `src/lib/db/migrations/`
- Implement `up()` and `down()` methods
- Run: `make migrate`

**Step 3: Create Repository** (`src/repos/my_entity_repo.py`)

```python
from src.shared.base.base_repo import BaseRepository
from src.entities.my_entity import MyEntity

class MyEntityRepository(BaseRepository):
    def __init__(self):
        super().__init__(MyEntity)

    def get_by_name(self, name: str):
        return MyEntity.select().where(MyEntity.name == name).first()
```

**Step 4: Create Service** (`src/services/my_entity_service.py`)

```python
from src.shared.base.base_service import BaseService
from src.repos.my_entity_repo import MyEntityRepository

class MyEntityService(BaseService):
    def __init__(self, repo: MyEntityRepository = None):
        if repo is None:
            repo = MyEntityRepository()
        super().__init__(repo)

    def custom_business_logic(self, entity_id: str):
        # Your business logic here
        return self.repo.get_by_id(entity_id)
```

**Step 5: Register in DI Container** (`src/app.py` → `setup_di_container()`)

```python
container.register_type(
    MyEntityRepository,
    lambda: MyEntityRepository(),
    singleton=False,
)
container.register_type(
    MyEntityService,
    lambda: MyEntityService(repo=container.resolve(MyEntityRepository)),
    singleton=False,
)
```

### 2️⃣ Creating DTOs for API/gRPC

**Request DTO** (`src/dtos/my_entity/req.py`)

```python
from pydantic import BaseModel, Field

class CreateMyEntityRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
```

**Response DTO** (`src/dtos/my_entity/res.py`)

```python
from pydantic import BaseModel
from datetime import datetime

class MyEntityResponse(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

### 3️⃣ Creating gRPC Service

**Define Proto** (`src/proto/my_entity.proto`)

```protobuf
syntax = "proto3";

package myentity;

message CreateMyEntityRequest {
    string name = 1;
    string description = 2;
}

message MyEntityResponse {
    string id = 1;
    string name = 2;
    string description = 3;
    int64 created_at = 4;
}

service MyEntityService {
    rpc Create(CreateMyEntityRequest) returns (MyEntityResponse);
    rpc GetById(GetByIdRequest) returns (MyEntityResponse);
}
```

**Generate Code** (`make grpc-generate`)

**Implement Servicer** (`src/grpc/my_entity_servicer.py`)

```python
from src.grpc_generated.my_entity_pb2_grpc import MyEntityServiceServicer
from src.grpc_generated.my_entity_pb2 import MyEntityResponse
from src.services.my_entity_service import MyEntityService

class MyEntityServicer(MyEntityServiceServicer):
    def __init__(self, service: MyEntityService):
        self.service = service

    def Create(self, request, context):
        entity = self.service.create({
            "name": request.name,
            "description": request.description,
        })
        return MyEntityResponse(id=entity.id, name=entity.name, ...)
```

### 4️⃣ Handling Kafka Events

**Publish Event** (from a service)

```python
from src.lib.event_bus.kafka.producer import KafkaProducerImpl

class MyEntityService(BaseService):
    def create(self, data):
        entity = super().create(data)

        # Publish event
        producer = KafkaProducerImpl(topic="my-entity-events")
        producer.produce(
            key=entity.id,
            value={"event": "entity_created", "entity_id": entity.id}
        )
        return entity
```

**Consume Event** (`src/handlers/my_entity_events.py`)

```python
from src.shared.base.base_handler import BaseEventHandler

class MyEntityEventHandler(BaseEventHandler):
    def handle(self, event_data):
        if event_data.get("event") == "entity_created":
            entity_id = event_data.get("entity_id")
            # Handle the event
            print(f"Entity created: {entity_id}")
```

**Register Handler** (`src/handlers/event_dispatcher.py`)

```python
from src.handlers.my_entity_events import MyEntityEventHandler

def initialize_event_handlers():
    handlers = {
        "my-entity-events": MyEntityEventHandler(),
    }
    # Register handlers with consumer
```

### 5️⃣ Using LLM Providers

**Available Implementations**: `Gemini`, `OpenAI`, `Ollama`

```python
from src.lib.llm.gemini import GeminiLLM
from src.lib.llm.dtos import TextGenerationRequest

class DocumentAnalysisService(BaseService):
    def analyze_text(self, text: str) -> str:
        llm = GeminiLLM()
        request = TextGenerationRequest(
            prompt=f"Analyze: {text}",
            max_tokens=500,
        )
        response = llm.generate(request)
        return response.text
```

### 6️⃣ Using OCR

```python
from src.lib.ocr.paddleocrvl import PaddleOCRVL
from src.lib.ocr.dtos import ImageOCRRequest

class DocumentExtractionService(BaseService):
    def extract_text(self, image_path: str) -> dict:
        ocr = PaddleOCRVL()
        request = ImageOCRRequest(image_path=image_path)
        result = ocr.recognize(request)
        return {
            "text": result.text,
            "layout": result.layout_info,
            "confidence": result.confidence,
        }
```

---

## 🧪 Testing Conventions

### Unit Tests

```python
# tests/test_my_entity_service.py
import pytest
from src.services.my_entity_service import MyEntityService
from src.repos.my_entity_repo import MyEntityRepository

class TestMyEntityService:
    @pytest.fixture
    def service(self):
        repo = MyEntityRepository()
        return MyEntityService(repo)

    def test_get_by_name(self, service):
        # Test implementation
        pass
```

### Running Tests

```bash
make test           # All tests with coverage
pytest tests/       # Specific test file
pytest -k "test_pattern" -v  # Filtered tests
```

---

## ⚙️ Configuration & Environment

All settings come from environment variables via `src/settings.py` (Pydantic):

| Variable                  | Default                  | Purpose                    |
| ------------------------- | ------------------------ | -------------------------- |
| `APP_NAME`                | FastAPI Minimal Template | Application name           |
| `DEBUG`                   | false                    | Debug mode                 |
| `DATABASE_URL`            | sqlite:///db.sqlite      | Peewee database connection |
| `REDIS_URL`               | redis://localhost:6379/0 | Redis cache URL            |
| `KAFKA_BOOTSTRAP_SERVERS` | localhost:9092           | Kafka brokers              |
| `GEMINI_API_KEY`          | (empty)                  | Google Gemini API key      |
| `OLLAMA_BASE_URL`         | http://localhost:11434   | Ollama server URL          |
| `OPENAI_API_KEY`          | (empty)                  | OpenAI API key             |

---

## 🔗 Integration Points

### With Backend Service

- **gRPC Calls**: Use `src/grpc/client.py` to call backend services
- **Shared Models**: Coordinate proto definitions and DTOs with backend
- **Event Topics**: Align Kafka topics across services

### With External Services

- **S3 Storage**: `src/lib/s3_client.py` handles file uploads/downloads
- **LLM APIs**: Configure keys in `.env` for Gemini, OpenAI, etc.
- **Database**: Use provided connection string for data persistence

---

## 📋 Before Starting Work

1. **Check existing patterns** — Look for similar implementations in current codebase
2. **Use base classes** — Inherit from `BaseEntity`, `BaseService`, `BaseRepository` to maintain consistency
3. **Follow naming conventions** — Entities end in `-Entity`, services in `-Service`, repos in `-Repository`
4. **Register in DI** — New services must be registered in `setup_di_container()`
5. **Write tests first** — Create tests in `tests/` before implementing features
6. **Update proto files** — If adding gRPC methods, update `.proto` and regenerate
7. **Run linters** — `make lint && make format` before committing
8. **Document changes** — Update this guide if adding new patterns or layers

---

## 🚀 Deployment Tips

- **Docker Build**: `docker build -t ai-service:latest .`
- **Environment**: Set all required env vars before deploying
- **Migrations**: Run `make migrate` after deploying new versions
- **Health Check**: Endpoint available at `GET /api/health`
- **gRPC Port**: Default `50051`, ensure it's exposed in deployment

---

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [gRPC Python Guide](https://grpc.io/docs/languages/python/)
- [Peewee ORM Docs](http://docs.peewee-orm.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Kafka Python Client](https://github.com/confluentinc/confluent-kafka-python)

---

**Last Updated**: March 2026 | Use this guide when adding features, fixing bugs, or onboarding new developers.
