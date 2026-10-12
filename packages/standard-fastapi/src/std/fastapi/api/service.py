"""Base class that registers a service's routes on an injected application."""

from __future__ import annotations

from abc import ABC, abstractmethod

from fastapi import FastAPI


class APIService(ABC):
    """Attach one route group to an existing FastAPI application."""

    def __init__(self, app: FastAPI, name: str | None = None) -> None:
        """Store the app and register routes implemented by the subclass."""
        self.app = app
        self.name = name or type(self).__name__
        self._setup_routes()

    @abstractmethod
    def _setup_routes(self) -> None:
        """Register this service's routes on :attr:`app`."""
