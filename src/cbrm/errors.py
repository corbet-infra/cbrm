"""Errors every interface maps the same way (CLI exit, HTTP status, MCP tool error)."""


class PanelError(RuntimeError):
    """The panel answered unexpectedly (login failed, HTTP error, unexpected content)."""


class ContractError(PanelError):
    """The panel no longer looks the way a feature relies on. Nothing was sent."""


class ServiceError(ValueError):
    """The request is refused by cbrm's rules (unknown VM, missing confirmation, bad argument)."""
