from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.error import KafkaError
from typing import Callable, Optional, Any
from src.lib.event_bus.base.base_consumer import BaseConsumer
from src.settings import get_settings
import logging
import threading

logger = logging.getLogger(__name__)


class KafkaConsumerImpl(BaseConsumer):
    """Kafka consumer implementation using Confluent Kafka"""

    def __init__(
        self, topics: list[str], handler: Callable[[str, dict[str, Any]], None]
    ):
        super().__init__(topics, handler)
        settings = get_settings()

        try:
            # Convert list of bootstrap servers to comma-separated string
            bootstrap_servers = (
                ",".join(settings.kafka_bootstrap_servers)
                if isinstance(settings.kafka_bootstrap_servers, list)
                else settings.kafka_bootstrap_servers
            )

            self.consumer = Consumer(
                {
                    "bootstrap.servers": bootstrap_servers,
                    "group.id": settings.kafka_consumer_group_id,
                    "auto.offset.reset": settings.kafka_consumer_auto_offset_reset,
                    "enable.auto.commit": True,
                    "enable.auto.offset.store": True,
                    "session.timeout.ms": 6000,
                    "socket.keepalive.enable": True,
                }
            )
            self.consumer.subscribe(topics)
            self.running = False
            self.consumer_thread = None
            logger.info(f"Kafka Consumer initialized for topics: {topics}")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka Consumer: {e}")
            raise

    def start(self):
        """Start consuming messages"""
        if not self.running:
            self.running = True
            self.consumer_thread = threading.Thread(
                target=self._consume_loop, daemon=True
            )
            self.consumer_thread.start()
            logger.info("Kafka Consumer started")

    def _consume_loop(self):
        """Main consume loop"""
        try:
            while self.running:
                # Poll for messages (timeout in seconds)
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    # Timeout, no message
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition
                        continue
                    else:
                        # Error occurred
                        logger.error(f"Kafka error: {msg.error()}")
                        continue

                try:
                    key = msg.key().decode("utf-8") if msg.key() else None
                    value = msg.value().decode("utf-8") if msg.value() else None
                    self._handle_message(key, value)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except KafkaError as e:
            logger.error(f"Kafka error during consumption: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in consumption loop: {e}")
        finally:
            self.consumer.close()

    def stop(self):
        """Stop consuming messages"""
        self.running = False
        if self.consumer_thread:
            self.consumer_thread.join(timeout=5)
        logger.info("Kafka Consumer stopped")

    def close(self):
        """Close consumer connection"""
        try:
            self.stop()
            if self.consumer:
                self.consumer.close()
            logger.info("Kafka Consumer closed")
        except Exception as e:
            logger.error(f"Error closing Kafka Consumer: {e}")
