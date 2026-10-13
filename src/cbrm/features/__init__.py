"""Every feature cbrm offers, registered in REGISTRY (see registry.py for the rules)."""
from . import account, backups, billing, media, naming, network, stats, tasks, vm  # noqa: F401  (importing registers the features)
from .registry import REGISTRY, RISKS, Ctx, Feature, Param

__all__ = ["REGISTRY", "RISKS", "Ctx", "Feature", "Param"]
