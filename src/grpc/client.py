"""
gRPC client example for ProjectMetadata service

Usage:
    python -m src.grpc.client
"""

import grpc
from src.grpc_generated.project_metadata_pb2 import (
    ProjectMetadataRequest,
    ProjectMetadataIdRequest,
)
from src.settings import get_settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Example client usage"""
    settings = get_settings()
    grpc_host = f"{settings.host}:{settings.grpc_port}"

    try:
        # Create channel
        channel = grpc.aio.secure_channel(grpc_host, grpc.aio.ssl_channel_credentials())
        logger.info(f"Connected to gRPC server at {grpc_host}")

        # Example: Create project
        # Note: In production, use the generated stub from protoc
        # stub = project_metadata_pb2_grpc.ProjectMetadataServiceStub(channel)
        # response = stub.CreateProject(ProjectMetadataRequest(
        #     name="Test Project",
        #     description="A test project",
        #     version="1.0.0"
        # ))
        # logger.info(f"Created project: {response.id}")

        print(f"gRPC server should be running at {grpc_host}")
        print("To use this client, generate gRPC stubs with protoc:")
        print(
            "  python -m grpc_tools.protoc -I./src/proto --python_out=./src/grpc_generated --grpc_python_out=./src/grpc_generated ./src/proto/project_metadata.proto"
        )

    except Exception as e:
        logger.error(f"Error connecting to gRPC server: {e}")


if __name__ == "__main__":
    main()
