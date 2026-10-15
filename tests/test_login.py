"""The panel login: since 2026-10-15 a Livewire component (auth.login), no plain form."""
import html
import json

import httpx
import pytest

from cbrm.errors import ContractError, PanelError
from cbrm.panel import BASE, Panel

SNAPSHOT = json.dumps({"data": {"email": "", "password": "", "step": 1}, "memo": {"name": "auth.login"}, "checksum": "x"})


def login_page(submit="login", models=("email", "password")):
    fields = "".join(f'<input wire:model="{m}">' for m in models)
    return (f'<html><head><meta name="csrf-token" content="tok"></head><body>'
            f'<script data-update-uri="/livewire-abc/update"></script>'
            f'<div wire:snapshot="{html.escape(SNAPSHOT)}"><form wire:submit="{submit}">{fields}</form></div></body></html>')


def panel(tmp_path, page, answer):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/login":
            return httpx.Response(200, text=page)
        if request.method == "POST" and request.url.path == "/livewire-abc/update":
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"components": [{"snapshot": SNAPSHOT, "effects": answer}]})
        return httpx.Response(404)

    p = Panel("user@example.org", "secret", state_dir=tmp_path)
    p.http = httpx.Client(base_url=BASE, transport=httpx.MockTransport(handler))
    return p, sent


def test_login_sends_the_credentials_and_follows_the_redirect(tmp_path):
    p, sent = panel(tmp_path, login_page(), {"redirect": f"{BASE}/customer/dashboard"})
    p._login()
    component = sent[0]["components"][0]
    assert sent[0]["_token"] == "tok"
    assert component["updates"] == {"email": "user@example.org", "password": "secret"}
    assert [c["method"] for c in component["calls"]] == ["login"]
    assert (tmp_path / "cookies.json").exists()


@pytest.mark.parametrize("answer", [{}, {"redirect": f"{BASE}/login"}])
def test_login_without_a_redirect_away_from_the_login_fails(tmp_path, answer):
    p, _ = panel(tmp_path, login_page(), answer)
    with pytest.raises(PanelError, match="login failed"):
        p._login()


def test_a_changed_login_form_sends_nothing(tmp_path):
    p, sent = panel(tmp_path, login_page(submit="authenticate"), {"redirect": f"{BASE}/customer/dashboard"})
    with pytest.raises(ContractError):
        p._login()
    assert sent == []
