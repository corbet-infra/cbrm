"""cbrm — BERO HOST management. `Panel` drives the customer panel, `Console` its VNC console."""
from .console import Console
from .errors import ContractError, PanelError, ServiceError
from .panel import Panel

__all__ = ["Panel", "PanelError", "ContractError", "ServiceError", "Console"]
__version__ = "0.6.0"
