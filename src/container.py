from typing import Type, TypeVar, Dict, Callable, Any, Optional
import logging
import inspect

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DIContainer:
    """Dependency Injection Container for managing dependencies"""

    def __init__(self):
        self._singletons: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._type_mappings: Dict[Type, str] = {}  # Map types to keys

    def register_singleton(self, key: str, instance: Any) -> None:
        """Register a singleton instance"""
        self._singletons[key] = instance
        # Register type mapping if instance has a type
        instance_type = type(instance)
        self._type_mappings[instance_type] = key
        logger.info(f"Registered singleton: {key}")

    def register_factory(
        self, key: str, factory: Callable, return_type: Optional[Type] = None
    ) -> None:
        """Register a factory function"""
        self._factories[key] = factory
        if return_type:
            self._type_mappings[return_type] = key
        logger.info(f"Registered factory: {key}")

    def register_type(
        self, service_type: Type[T], factory: Callable, singleton: bool = True
    ) -> None:
        """Register a service type with its factory"""
        key = service_type.__name__
        if singleton:
            # Create instance immediately for singleton
            instance = factory()
            self.register_singleton(key, instance)
        else:
            self.register_factory(key, factory, service_type)

    def get(self, key: str) -> Any:
        """Get instance by key"""
        # Check singletons first
        if key in self._singletons:
            return self._singletons[key]

        # Check factories
        if key in self._factories:
            factory = self._factories[key]
            instance = factory()
            return instance

        raise KeyError(f"Dependency not found: {key}")

    def get_singleton(self, key: str) -> Any:
        """Get singleton instance"""
        if key not in self._singletons:
            raise KeyError(f"Singleton not found: {key}")
        return self._singletons[key]

    def resolve(self, service_type: Type[T]) -> T:
        """Resolve a service type by resolving its dependencies"""
        # Check type mapping first
        key = self._type_mappings.get(service_type)
        if key:
            return self.get(key)

        # Try by type name
        key = service_type.__name__
        if key in self._singletons or key in self._factories:
            return self.get(key)

        raise KeyError(f"Service type not found: {service_type.__name__}")

    def close_all(self) -> None:
        """Close all singletons that have close method"""
        for key, instance in self._singletons.items():
            if hasattr(instance, "close"):
                try:
                    instance.close()
                    logger.info(f"Closed singleton: {key}")
                except Exception as e:
                    logger.error(f"Error closing singleton {key}: {e}")


# Global DI container instance
_di_container: Optional[DIContainer] = None


def get_di_container() -> DIContainer:
    """Get or create global DI container"""
    global _di_container
    if _di_container is None:
        _di_container = DIContainer()
    return _di_container


def initialize_di_container(container: Optional[DIContainer] = None) -> DIContainer:
    """Initialize DI container with dependencies"""
    global _di_container
    _di_container = container or DIContainer()
    return _di_container
