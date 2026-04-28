from confluent_kafka import Producer
from confluent_kafka.error import KafkaError
from typing import Optional, Any, Callable
from src.lib.event_bus.base.base_producer import BaseProducer
from src.settings import get_settings
import logging

logger = logging.getLogger(__name__)


class KafkaProducerImpl(BaseProducer):
    """Kafka producer implementation using Confluent Kafka"""

    def __init__(self, topic: str, on_delivery: Optional[Callable] = None):
        super().__init__(topic)
        settings = get_settings()

        try:
            # Convert list of bootstrap servers to comma-separated string
            bootstrap_servers = (
                ",".join(settings.kafka_bootstrap_servers)
                if isinstance(settings.kafka_bootstrap_servers, list)
                else settings.kafka_bootstrap_servers
            )

            self.producer = Producer(
                {
                    "bootstrap.servers": bootstrap_servers,
                    "client.id": f"fastapi-producer-{topic}",
                    "acks": "all",
                    "retries": 3,
                    "linger.ms": 10,
                }
            )
            self.on_delivery = on_delivery or self._default_delivery_report
            logger.info(f"Kafka Producer initialized for topic: {topic}")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka Producer: {e}")
            raise

    def _default_delivery_report(self, err, msg):
        """Default delivery report callback"""
        if err is not None:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.info(
                f"Message delivered to {msg.topic()} "
                f"[{msg.partition()}] at offset {msg.offset()}"
            )

    def send(
        self,
        key: Optional[str],
        value: dict[str, Any],
        topic: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """Send message to Kafka topic"""
        try:
            key_bytes = key.encode("utf-8") if key else None
            value_bytes = self._serialize_value(value).encode("utf-8")

            topic_to_use = topic or self.topic
            self.producer.produce(
                topic_to_use,
                key=key_bytes,
                value=value_bytes,
                callback=self.on_delivery,
            )

            # Non-blocking call, messages are queued
            # Poll to handle callbacks
            self.producer.poll(0)
            return True
        except KafkaError as e:
            logger.error(f"Kafka error sending message: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    def flush(self, timeout: int = 30) -> int:
        """Flush pending messages"""
        try:
            remaining = self.producer.flush(timeout)
            if remaining > 0:
                logger.warning(
                    f"Failed to deliver {remaining} messages within {timeout}s"
                )
            return remaining
        except Exception as e:
            logger.error(f"Error flushing producer: {e}")
            return -1

    def close(self):
        """Close producer connection"""
        try:
            self.flush()
            self.producer.close()
            logger.info("Kafka Producer closed")
        except Exception as e:
            logger.error(f"Error closing Kafka Producer: {e}")
