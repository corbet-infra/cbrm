"""Regression tests for the findings of the second independent review: each test here fails on the code
as it was before the fix. The panel is mocked (no network), see test_wave2.py and test_service.py."""
import json
import re
from dataclasses import replace

import pytest

from cbrm.errors import ContractError, PanelError, ServiceError
from cbrm.features import REGISTRY, registry
from cbrm.service import Service

import test_service
from test_wave2 import A, ACCOUNT, EMPTY, P, PRODUCT, fingerprint, make_key, sent_nothing, svc_for


@pytest.fixture
def svc(tmp_path):
    return svc_for(tmp_path)


# -- 4: an unknown verification stays unknown -------------------------------------------------------------

@pytest.mark.parametrize("answer,expected", [(None, None), (True, True), (False, False), (0, False), ("yes", True)])
def test_verified_none_is_not_turned_into_false(tmp_path, monkeypatch, answer, expected):
    svc = Service(test_service.FakePanel(tmp_path), allow=["1"])
    monkeypatch.setitem(registry.REGISTRY, "power", replace(registry.REGISTRY["power"], verify=lambda *a, **k: answer))
    r = svc.run("power", "1", {"action": "restart"}, confirm="1")
    assert r["verified"] is expected and "verify_error" not in r
    assert f"verified={expected}" in svc.audit_path.read_text()
