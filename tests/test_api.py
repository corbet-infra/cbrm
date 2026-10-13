"""The HTTP API: every route needs the token, including the schema; odd tokens are a 401, not a 500."""
import pytest
from fastapi.testclient import TestClient

from cbrm.api import create_app
from cbrm.service import Service

from test_service import FakePanel


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CBRM_API_TOKEN", "right-token")
    return TestClient(create_app(Service(FakePanel(tmp_path), allow=["1"])))


@pytest.mark.parametrize("path", ["/features", "/openapi.json", "/vms", "/vms/1/status"])
def test_every_route_needs_the_token(client, path):
    assert client.get(path).status_code in (401, 403)
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_framework_docs_routes_are_gone(client, path):
    assert client.get(path, headers={"Authorization": "Bearer right-token"}).status_code == 404


def test_odd_token_is_refused_not_crashing(client):
    assert client.get("/features", headers={"Authorization": "Bearer töken".encode("latin-1")}).status_code == 401


def test_schema_with_token(client):
    r = client.get("/openapi.json", headers={"Authorization": "Bearer right-token"})
    assert r.status_code == 200 and r.json()["info"]["title"] == "cbrm"


def test_changes_need_confirmation_over_http(client):
    h = {"Authorization": "Bearer right-token"}
    r = client.post("/vms/1/power", json={"args": {"action": "restart"}}, headers=h)
    assert r.status_code == 403 and r.json()["kind"] == "refused"
    assert client.get("/vms/1/power", params={"action": "restart"}, headers=h).status_code == 403
