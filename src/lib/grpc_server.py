import grpc
import logging
from concurrent import futures
from threading import Thread
from src.settings import get_settings


logger = logging.getLogger(__name__)


class GRPCServerManager:
    """Manages gRPC server lifecycle"""

    def __init__(self):
        self.server = None
        self.server_thread = None
        self.running = False

    def start(self):
        """Start gRPC server"""
        settings = get_settings()

        try:
            # Create gRPC server
            self.server = grpc.server(
                futures.ThreadPoolExecutor(max_workers=10),
                options=[
                    ("grpc.max_send_message_length", -1),
                    ("grpc.max_receive_message_length", -1),
                ],
            )

            # Add servicers using generated handler registration
            # servicer = ProjectMetadataGrpcServicer()
            # add_ProjectMetadataServiceServicer_to_server(servicer, self.server)

            # Bind to address
            grpc_host = f"{settings.host}:{settings.grpc_port}"
            self.server.add_insecure_port(grpc_host)

            # Start in background thread
            self.running = True
            self.server_thread = Thread(target=self._run_server, daemon=True)
            self.server_thread.start()

            logger.info(f"gRPC server started on {grpc_host}")
        except Exception as e:
            logger.error(f"Error starting gRPC server: {e}")
            raise

    def _run_server(self):
        """Run server in background thread"""
        try:
            self.server.start()
            self.server.wait_for_termination()
        except Exception as e:
            logger.error(f"Error in gRPC server thread: {e}")

    def stop(self):
        """Stop gRPC server"""
        if self.server and self.running:
            self.running = False
            grace_period = 5
            self.server.stop(grace_period)

            if self.server_thread:
                self.server_thread.join(timeout=grace_period + 1)

            logger.info("gRPC server stopped")

    def close(self):
        """Close gRPC server"""
        self.stop()


_grpc_server_manager: GRPCServerManager | None = None


def get_grpc_server_manager() -> GRPCServerManager:
    """Get or create gRPC server manager instance"""
    global _grpc_server_manager
    if _grpc_server_manager is None:
        _grpc_server_manager = GRPCServerManager()
    return _grpc_server_manager
