"""Tiny startup-time dependency registry.

ponytail: this replaces six copy-pasted set_X/get_X pairs that each held a
module-global singleton and repeated the same 503-when-uninitialised guard.
FastAPI's own ``app.state`` would also work, but the routers here are wired by
plain function calls in ``app._wire_dependencies`` and exercised directly in
tests, so a dict keeps both paths working without threading an app object
through every module.
"""

from typing import Generic, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


class Registry(Generic[T]):
    """Holds one instance of ``T``, registered at startup.

    Args:
        name: Human-readable service name used in the 503 message.
    """

    __slots__ = ("_name", "_instance")

    def __init__(self, name: str) -> None:
        self._name = name
        self._instance: T | None = None

    def set(self, instance: T) -> None:
        """Register the instance. Called once during startup wiring."""
        self._instance = instance

    def get(self) -> T:
        """Return the instance, or 503 if startup never registered one."""
        if self._instance is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"{self._name} service not initialised. Check server configuration."
                ),
            )
        return self._instance
