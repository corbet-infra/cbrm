"""A VM's own internal-network membership (connect, disconnect, change the internal IP) against reduced renderings
of the product page's "internal-network" card (tests/fixtures/vm_network_*.html; anonymised, no account data) and a
fake panel without network.

The connected card was recorded from the live panel. The unconnected card was not on screen (no VM was free to look
at), so `vm_network_free.html` is synthetic: the plain Livewire shape the connected card implies."""
from pathlib import Path

import pytest

from cbrm.errors import ContractError, ServiceError
from cbrm.features import REGISTRY
from cbrm.service import Service

FIX = Path(__file__).parent / "fixtures"
CONNECTED, FREE = (FIX / "vm_network_connected.html").read_text(), (FIX / "vm_network_free.html").read_text()
PAGE = "/customer/products/4"


class Resp:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body

    def raise_for_status(self):
        pass


class Http:
    def __init__(self, panel):
        self.panel, self.log, self.on = panel, [], {}

    def post(self, url, headers=None, json=None, data=None, files=None):
        c = json["components"][0]
        snap = __import__("json").loads(c["snapshot"])
        data = snap["data"]
        self.log.append((c["updates"], [(x["method"], x["params"]) for x in c["calls"]]))
        data.update(c["updates"])
        for call in c["calls"]:
            self.on.get(call["method"], lambda d, p: None)(data, call["params"])
        return Resp({"components": [{"snapshot": __import__("json").dumps({"data": data, "memo": snap["memo"]}),
                                     "effects": {"dispatches": [{"name": "notify", "params": ["saved"]}]}}]})


class FakePanel:
    def __init__(self, tmp, page):
        self.state_dir, self.pages = tmp, {PAGE: page}
        self.http = Http(self)

    def products(self):
        return {"9001": "4", "9002": "5"}

    def page(self, path):
        return self.pages[path]


def make(tmp_path, page=CONNECTED):
    return Service(FakePanel(tmp_path, page), allow=["9001"])


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    from cbrm.features import common
    monkeypatch.setattr(common.time, "sleep", lambda s: None)


def sent(svc):
    return svc.panel.http.log


# -- risk classes and doctor -------------------------------------------------------------------------

def test_the_three_are_change_features():
    for name in ("network-connect", "network-disconnect", "network-address-set"):
        assert REGISTRY[name].risk == "change" and REGISTRY[name].verify and REGISTRY[name].check


def test_changes_need_confirmation(tmp_path):
    svc = make(tmp_path)
    for name, args in (("network-disconnect", {}), ("network-address-set", {"address": "10.0.1.1"}), ("network-connect", {"network": "7"})):
        with pytest.raises(ServiceError, match="confirm"):
            svc.run(name, "9001", args)
    assert sent(svc) == []


@pytest.mark.parametrize("page", [CONNECTED, FREE])
def test_doctor_is_ok_in_both_states(tmp_path, page):
    res = make(tmp_path, page).check("9001")
    assert [res[n] for n in ("network-connect", "network-disconnect", "network-address-set")] == ["ok"] * 3


def test_doctor_reports_a_changed_card(tmp_path):
    res = make(tmp_path, CONNECTED.replace('wire:submit="saveAddress"', 'wire:submit="save"')).check("9001")
    assert res["network-address-set"].startswith("BROKEN") and "saveAddress" in res["network-address-set"]
    res = make(tmp_path, FREE.replace('wire:click="connect"', 'wire:click="connectA" data-x="1" ')
               .replace("</select>", '</select><button wire:click="connectB">b</button>')).check("9001")
    assert res["network-connect"].startswith("BROKEN")


# -- change the address --------------------------------------------------------------------------------

def test_address_set_sends_the_card_s_own_calls_and_verifies(tmp_path):
    svc = make(tmp_path)
    svc.panel.http.on["saveAddress"] = lambda d, p: svc.panel.pages.update({PAGE: CONNECTED.replace("10.0.1.10", "10.0.1.1")})
    out = svc.run("network-address-set", "9001", {"address": " 10.0.1.1 "}, confirm="9001")
    assert sent(svc) == [({"address": "10.0.1.1"}, [("saveAddress", [])])]
    assert out["result"]["address"] == "10.0.1.1" and out["result"]["was"] == "10.0.1.10" and out["verified"] is True


def test_address_set_not_applied_is_reported_unverified(tmp_path):
    svc = make(tmp_path)
    assert svc.run("network-address-set", "9001", {"address": "10.0.1.7"}, confirm="9001")["verified"] is False


@pytest.mark.parametrize("address", ["10.0.1.10", "10.0.2.5", "10.0.1.0", "10.0.1.255", "10.0.1", "nonsense", "::1", "10.0.1.1/24"])
def test_address_set_refuses_what_cannot_be_right(tmp_path, address):
    svc = make(tmp_path)
    with pytest.raises(ServiceError):
        svc.run("network-address-set", "9001", {"address": address}, confirm="9001")
    assert sent(svc) == []


def test_address_set_dry_run_and_unconnected(tmp_path):
    svc = make(tmp_path)
    out = svc.run("network-address-set", "9001", {"address": "10.0.1.1"}, dry_run=True)
    assert out["dry_run"] and "saveAddress" in out["would"] and sent(svc) == []
    with pytest.raises(ServiceError, match="not connected"):
        make(tmp_path, FREE).run("network-address-set", "9001", {"address": "10.0.1.1"}, confirm="9001")


def test_address_set_follows_the_allow_list(tmp_path):
    with pytest.raises(ServiceError, match="allow-list"):
        make(tmp_path).run("network-address-set", "9002", {"address": "10.0.1.1"}, confirm="9002")


# -- disconnect -----------------------------------------------------------------------------------------

def test_disconnect(tmp_path):
    svc = make(tmp_path)
    svc.panel.http.on["disconnect"] = lambda d, p: svc.panel.pages.update({PAGE: FREE})
    out = svc.run("network-disconnect", "9001", confirm="9001")
    assert sent(svc) == [({}, [("disconnect", [])])]
    assert out["result"]["network"] == "7" and out["result"]["was"] == "10.0.1.10" and out["verified"] is True


def test_disconnect_refuses_an_unconnected_vm_and_dry_runs(tmp_path):
    with pytest.raises(ServiceError, match="not connected"):
        make(tmp_path, FREE).run("network-disconnect", "9001", confirm="9001")
    svc = make(tmp_path)
    assert svc.run("network-disconnect", "9001", dry_run=True)["dry_run"] and sent(svc) == []


# -- connect --------------------------------------------------------------------------------------------

def test_connect(tmp_path):
    svc = make(tmp_path, FREE)
    svc.panel.http.on["connect"] = lambda d, p: svc.panel.pages.update({PAGE: CONNECTED})
    out = svc.run("network-connect", "9001", {"network": "7"}, confirm="9001")
    assert sent(svc) == [({"selectedNetworkId": "7"}, [("connect", [])])]
    assert out["result"]["connected"] is True and out["result"]["address"] == "10.0.1.10" and out["verified"] is True


def test_connect_refuses_a_network_the_panel_does_not_offer_and_a_connected_vm(tmp_path):
    svc = make(tmp_path, FREE)
    for bad in ("99", "7;x", ""):
        with pytest.raises(ServiceError):
            svc.run("network-connect", "9001", {"network": bad}, confirm="9001")
    with pytest.raises(ServiceError, match="already connected"):
        make(tmp_path).run("network-connect", "9001", {"network": "7"}, confirm="9001")
    assert sent(svc) == []
    assert svc.run("network-connect", "9001", {"network": "8"}, dry_run=True)["dry_run"] and sent(svc) == []


def test_a_card_that_looks_different_sends_nothing(tmp_path):
    svc = make(tmp_path, CONNECTED.replace('id="internalAddress"', 'id="other"'))
    with pytest.raises(ContractError):
        svc.run("network-address-set", "9001", {"address": "10.0.1.1"}, confirm="9001")
    svc = make(tmp_path, CONNECTED.replace('title="Interne IP"', 'title="IP"'))
    with pytest.raises(ContractError):
        svc.run("network-disconnect", "9001", confirm="9001")
    assert sent(svc) == []
