"""
Base plugin class for Alps Toolkit.

To create a new plugin:
  1. Create a file in app/plugins/
  2. Define a class that extends ToolkitPlugin
  3. Implement the required properties and register_routes()
  4. The plugin is auto-discovered on startup

Example:
    class MyPlugin(ToolkitPlugin):
        id = "my_tool"
        name = "My Tool"
        icon = "🔧"
        order = 99

        def register_routes(self, app):
            @app.get(f"/api/{self.id}/hello")
            async def hello():
                return {"msg": "world"}
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from fastapi import FastAPI


class ToolkitPlugin(ABC):
    """Base class every plugin must extend."""

    id: str = ""          # URL-safe identifier (e.g. "gps_server")
    name: str = ""        # Human label shown in nav
    icon: str = "🔧"      # Emoji icon
    order: int = 50       # Sort order in nav (lower = first)

    @abstractmethod
    def register_routes(self, app: FastAPI):
        """Add API routes (and optional WebSocket endpoints) to *app*."""

    def startup(self):
        """Called once after all plugins are registered."""

    def shutdown(self):
        """Called on app shutdown."""

    def manifest(self) -> dict:
        """Return JSON-serializable metadata for the frontend."""
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "order": self.order,
        }
