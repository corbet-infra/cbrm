"""Every feature cbrm offers, registered in REGISTRY (see registry.py for the rules)."""
from . import (  # noqa: F401  (importing registers the features)
    account,
    accounting,
    activity,
    backups,
    billing,
    codes,
    internal_networks,
    media,
    naming,
    network,
    stats,
    tasks,
    tickets,
    vm,
    vm_firewall,
    vm_network,
)
from .registry import FILE_TYPES, REGISTRY, RISKS, Ctx, Feature, Param

__all__ = ["FILE_TYPES", "REGISTRY", "RISKS", "Ctx", "Feature", "Param"]
