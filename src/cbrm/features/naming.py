"""Names: the VM's host name and the product's display name."""
from __future__ import annotations

from .common import clean, dns_name, limits, ok, post_form, require_element, require_post, text, tolerant
from .registry import Param, feature


def _check_hostname(ctx, vm):
    page = ctx.product_page(vm)
    path = f"/customer/rootserver/{vm}/sethostname"
    page.require_endpoint(path)
    require_post(page, path, "hostname")
    require_element(page, "#hostname", "the host name display")
    return page, path


@tolerant
def _verify_hostname(ctx, vm, result, hostname):
    return ok(result) and text(require_element(ctx.fresh(vm), "#hostname", "the host name display")) == result["wanted"]


@feature("hostname-set", "change", "Set the VM's host name in the panel (lower-cased; letters, digits, hyphens, dots)",
         (Param("hostname", "the new host name, e.g. web1.example.org"),), verify=_verify_hostname,
         check=_check_hostname)
def _hostname_set(ctx, vm, hostname):
    page, path = _check_hostname(ctx, vm)
    lo, hi = limits(page, "#hostnameChangeInput", "the host name field")
    hostname = dns_name(hostname, "hostname", lo, min(hi, 253))
    before = text(require_element(page, "#hostname", "the host name display"))
    return ctx.send(f"POST {path} hostname={hostname!r} (was {before!r})",
                    lambda: {**post_form(ctx, page, path, {"hostname": hostname}), "wanted": hostname, "was": before})


def _check_rename(ctx, vm):
    page = ctx.product_page(vm)
    pid = ctx.panel.products()[vm]
    path = f"/customer/service/setdisplayname/{pid}"
    page.require_endpoint(path)
    require_post(page, path, "displayname")
    require_element(page, "#displayname", "the product name display")
    return page, path


@tolerant
def _verify_rename(ctx, vm, result, name):
    return ok(result) and text(require_element(ctx.fresh(vm), "#displayname", "the product name display")) == result["wanted"]


@feature("rename", "change", "Rename the product in the panel (its display name, not the host name)",
         (Param("name", "the new display name"),), verify=_verify_rename, check=_check_rename)
def _rename(ctx, vm, name):
    page, path = _check_rename(ctx, vm)
    lo, hi = limits(page, "#displaynameChangeInput", "the product name field")
    name = clean(name, "name", lo, hi)
    before = text(require_element(page, "#displayname", "the product name display"))
    return ctx.send(f"POST {path} displayname={name!r} (was {before!r})",
                    lambda: {**post_form(ctx, page, path, {"displayname": name}), "wanted": name, "was": before})
