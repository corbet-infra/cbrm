"""cbrm — BERO HOST management. `Panel` drives the customer panel, `Console` its VNC console."""
from .panel import Panel, PanelError
from .console import Console

__all__ = ["Panel", "PanelError", "Console"]
__version__ = "0.1.1"
