"""The account's bookkeeping pages (/customer/accounting), read only: invoices, orders and transactions.

Account-wide, like every `account-*` feature: the VM argument only names the account context (see `common`).
The lists are the panel's own Livewire tables, each with a search box and pages.
"""
from __future__ import annotations

import re

import httpx

from ..errors import ContractError, PanelError, ServiceError
from .common import panel_date, site_page
from .common import text as squash
from .registry import Param, feature

PAGE = "/customer/accounting"
LABELS = {"Rechnungen": "number", "Betrag": "amount", "Datum": "date", "Status": "status", "Vorgang": "description",
          "Produkt": "product", "Typ": "type"}


def _component(ctx, vm, name):
    return site_page(ctx, vm, PAGE).component(name)


def _rows(comp) -> list[dict]:
    out = []
    for row in comp.tree.css("div.grey-transparent-background"):
        item = {}
        for cell in row.css("p"):
            label = cell.css_first("b.d-xl-none")
            if label is None:
                continue
            key = LABELS.get(squash(label).rstrip(":").strip())
            if key is None:
                raise ContractError(f"{PAGE}: a column named {squash(label)!r}, which cbrm does not know")
            if key == "status":
                dot = cell.css_first("i")
                item[key] = (dot.attributes.get("data-bs-title") or
                             next((c.removeprefix("text-") for c in (dot.attributes.get("class") or "").split()
                                   if c.startswith("text-")), "")) if dot is not None else ""
                continue
            item[key] = squash(cell).removeprefix(squash(label)).strip()
            if key == "date":
                item[key] = panel_date(item[key])
        if item:
            out.append(item)
    return out


def _table(name: str, search_model: str, page_model: str):
    def read(ctx, vm, search=None, page=1):
        if not 1 <= page <= 1000:
            raise ServiceError("page must be 1..1000")
        comp = _component(ctx, vm, name).require(models=(search_model,))
        updates = {}
        if search:
            updates[search_model] = search.strip()
        if page != 1:
            updates[f"paginators.{page_model}"] = page
        if updates:
            comp = comp._send(updates, [])
        return {"rows": _rows(comp), "page": page, "more": "nextPage" in comp.html}

    def check(ctx, vm):
        comp = _component(ctx, vm, name).require(models=(search_model,))
        _rows(comp)
    return read, check


PARAMS = (Param("search", "only rows matching this text (the panel's own search)", required=False),
          Param("page", "page number, 1 is the newest", int, required=False, default=1))

_inv, _inv_check = _table("invoices-table", "searchInvoices", "invoicesPage")
_ord, _ord_check = _table("orders-table", "searchOrders", "ordersPage")
_trx, _trx_check = _table("transactions-table", "searchTransactions", "transactionsPage")

feature("account-invoices", "read", "Invoices of the account (account-wide): number, amount, date; newest first",
        PARAMS, check=_inv_check)(_inv)
feature("account-orders", "read", "Orders of the account (account-wide): product, type, date, status as the panel shows it",
        PARAMS, check=_ord_check)(_ord)
feature("account-transactions", "read",
        "Credit transactions of the account (account-wide): description, amount (negative = spent), date, status",
        PARAMS, check=_trx_check)(_trx)


# -- invoice PDFs -------------------------------------------------------------------------------------------

DOWNLOAD = "/customer/rechnungen/herunterladen/"
_INVOICE = re.compile(r"[0-9A-Za-z][0-9A-Za-z-]{0,39}")


def _invoice_links(comp) -> dict[str, str]:
    """Invoice number -> the path of its download link, from the invoices table's rows."""
    out = {}
    for a in comp.tree.css(f"a[href*='{DOWNLOAD}']"):
        path = httpx.URL(a.attributes.get("href") or "").path
        number = path.removeprefix(DOWNLOAD)
        if not path.startswith(DOWNLOAD) or not _INVOICE.fullmatch(number):
            raise ContractError(f"{PAGE}: an invoice download link cbrm cannot read")
        out[number] = path
    return out


def _check_invoice_pdf(ctx, vm):
    comp = _component(ctx, vm, "invoices-table").require(models=("searchInvoices",))
    rows, links = _rows(comp), _invoice_links(comp)
    if rows and not links:
        raise ContractError(f"{PAGE}: the invoices have no download links")


@feature("account-invoice-download", "read",
         "One invoice as PDF (account-wide): the panel's download of an invoice number from `account-invoices`",
         (Param("invoice", "the invoice number from `account-invoices`"),), returns="pdf", check=_check_invoice_pdf)
def _account_invoice_download(ctx, vm, invoice):
    number = str(invoice).strip()
    if not _INVOICE.fullmatch(number):
        raise ServiceError("an invoice is addressed by its number from `account-invoices`")
    comp = _component(ctx, vm, "invoices-table").require(models=("searchInvoices",))
    links = _invoice_links(comp)
    if number not in links:  # not on the first page: let the panel's own search find it
        links = _invoice_links(comp._send({"searchInvoices": number}, []))
    if number not in links:
        raise ServiceError(f"the account has no invoice {number!r} (see `account-invoices`)")
    body, kind = ctx.panel.download(links[number])
    if not body.startswith(b"%PDF"):
        raise PanelError(f"invoice {number}: the panel sent {kind or 'something'} instead of a PDF")
    return body
