"""Statistics: the numbers the panel's overview and its charts show (all read-only GETs the page itself makes)."""
from __future__ import annotations

from ..errors import ContractError, PanelError
from .common import get_json
from .registry import Param, feature

TIMEFRAMES = ("hour", "day", "week", "month", "year")
# metric -> (the panel's `data` parameter, series names, unit as the panel's chart labels it)
METRICS = {"cpu": ("cpu", ("cpu",), "%"), "ram": ("mem", ("ram",), "%"),
           "disk": ("diskread,diskwrite", ("read", "write"), "MB/s"), "network": ("netin,netout", ("in", "out"), "Mbit/s")}


def _need(d: dict, what: str, *keys: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ContractError(f"{what}: the answer lacks {', '.join(missing)}")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _check_stats(ctx, vm):
    page = ctx.product_page(vm)
    for e in ("updatestats", "live_statistics", "statistics"):
        page.require_endpoint(f"/customer/rootserver/{vm}/{e}")
    return page


@feature("stats", "read", "Show current CPU, RAM, disk and network use",
         "Current CPU, RAM and disk use, uptime, ping, traffic and running network/disk counters")
def _stats(ctx, vm):
    _check_stats(ctx, vm)
    d = get_json(ctx, f"/customer/rootserver/{vm}/updatestats")
    _need(d, "updatestats", "state")
    out = {"vm": vm, "panel_state": d["state"]}
    if d["state"] != "success":  # e.g. expired or offline: what the panel still reports
        out.update({k: d[k] for k in ("disk", "disk_percent", "uptime", "template_name") if k in d})
        return out
    _need(d, "updatestats", "state_text", "cpu_percent", "ram_percent", "current_memory", "memory", "cores", "disk",
          "disk_percent", "uptime", "current_traffic", "template_name", "ping")
    ping = _num(d["ping"])
    out.update({"state": d["state_text"], "cpu_percent": _num(d["cpu_percent"]), "cores": d["cores"],
                "ram_percent": _num(d["ram_percent"]), "ram_used": d["current_memory"], "ram_total": d["memory"],
                "disk_total": d["disk"], "disk_percent": _num(d["disk_percent"]), "uptime_seconds": d["uptime"],
                "ping_ms": ping if ping and ping > 0 else None, "traffic": d["current_traffic"],
                "template": d["template_name"], "rescue_system": bool(d.get("rescue_system"))})
    try:  # running counters the panel's live chart differences; not rates
        live = get_json(ctx, f"/customer/rootserver/{vm}/live_statistics")
        _need(live, "live_statistics", "netin", "netout", "diskread", "diskwrite")
        out["counters"] = {"net_in_bytes": live["netin"], "net_out_bytes": live["netout"],
                           "disk_read": live["diskread"], "disk_write": live["diskwrite"]}
    except PanelError:
        out["counters"] = None
    return out


@feature("stats-history", "read", "Show CPU, RAM, disk or network figures over time",
         "CPU, RAM, disk or network figures over a time frame: min, average, max and last "
         "value per series (cpu and ram in percent, disk in MB/s, network in Mbit/s)",
         (Param("timeframe", "how far back", choices=TIMEFRAMES, required=False, default="hour"),
          Param("metric", "what to show", choices=tuple(METRICS), required=False, default="cpu")))
def _stats_history(ctx, vm, timeframe="hour", metric="cpu"):
    _check_stats(ctx, vm)
    data_param, names, unit = METRICS[metric]
    d = get_json(ctx, f"/customer/rootserver/{vm}/statistics",
                 {"timeframe": timeframe, "type": "AVERAGE", "data": data_param})
    _need(d, "statistics", "labels", "data")
    labels, series = d["labels"], d["data"]
    if (not isinstance(labels, list) or not isinstance(series, list) or len(series) != len(names)
            or any(not isinstance(s, list) or len(s) != len(labels) for s in series)):
        raise ContractError("statistics: labels and data no longer line up the way the panel's chart reads them")
    out = []
    for name, values in zip(names, series, strict=True):
        nums = [n for n in map(_num, values) if n is not None]
        out.append({"name": name, "min": min(nums, default=None), "max": max(nums, default=None),
                    "average": round(sum(nums) / len(nums), 2) if nums else None,
                    "last": nums[-1] if nums else None})
    return {"timeframe": timeframe, "metric": metric, "unit": unit, "points": len(labels),
            "from": labels[0] if labels else None, "to": labels[-1] if labels else None, "series": out}
