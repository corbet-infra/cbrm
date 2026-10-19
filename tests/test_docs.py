"""The command reference (docs/command-reference.md, copied to the wiki) lists every registered feature as the
registry has it; summaries stay short; the scope is a field, stated where the docs explain the allow-list."""
from pathlib import Path

from cbrm.features import ACCOUNT_NOTE, REGISTRY

ROOT = Path(__file__).parents[1]
REGENERATE = "regenerate the command reference: python scripts/command_reference.py"


def _reference_rows() -> dict[str, str]:
    text = (ROOT / "docs" / "command-reference.md").read_text()
    return {line.split("`")[1]: line for line in text.splitlines() if line.startswith("| [`")}


def test_command_reference_lists_every_feature_with_its_risk_scope_and_summary():
    rows = _reference_rows()
    missing = sorted(set(REGISTRY) - set(rows))
    assert not missing, f"{REGENERATE}; missing: {missing}"
    wrong = [n for n, f in REGISTRY.items() if f"| {f.risk} | {f.scope} |" not in rows[n] or f.summary not in rows[n]]
    assert not wrong, f"{REGENERATE}; out of date: {wrong}"
    assert set(rows) <= set(REGISTRY), f"{REGENERATE}; unknown: {sorted(set(rows) - set(REGISTRY))}"


def test_command_reference_groups_every_feature():
    """`scripts/command_reference.py` writes the reference by area: a new feature needs a place there."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("command_reference", ROOT / "scripts" / "command_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    listed = [n for _, names in module.AREAS for n in names]
    assert sorted(listed) == sorted(REGISTRY), "add the feature to AREAS in scripts/command_reference.py"


def test_every_feature_has_a_short_summary_and_a_full_help():
    for name, f in REGISTRY.items():
        words = f.summary.split()
        assert 0 < len(words) <= 10, name
        assert f.summary[0].isupper() and not f.summary.endswith("."), name
        assert len(f.help.split()) >= len(words), name


def test_the_scope_is_a_field_not_prose():
    """`account-*` features have scope "account"; their help texts do not repeat it, the interfaces add it."""
    assert {n for n, f in REGISTRY.items() if f.scope == "account"} == {n for n in REGISTRY if n.startswith("account-")}
    repeated = [n for n, f in REGISTRY.items() if "account-wide" in f.help or "allow-list" in f.help]
    assert not repeated, f"the scope is shown from the field; drop it from the help of {repeated}"
    assert "not limited by the VM allow-list" in ACCOUNT_NOTE


def test_account_wide_features_are_documented_as_not_limited_by_the_allow_list():
    """The allow-list only decides which VM may name the account context; the docs and the skill must not let anyone
    believe it scopes `account-*` features."""
    phrase = "not limited by the VM allow-list"
    for doc in ("README.md", "skills/bero/SKILL.md", "docs/architecture.md", "docs/command-reference.md"):
        assert phrase in (ROOT / doc).read_text().replace("**", ""), doc


def test_mcp_tools_state_risk_and_scope():
    import asyncio

    from cbrm.mcp import mcp
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    for name, f in REGISTRY.items():
        doc = " ".join(tools["bero_" + name.replace("-", "_")].description.split())
        assert doc.startswith(f"[{f.risk}") and f.help in doc, name
        assert ("not limited by the VM allow-list" in doc) == (f.scope == "account"), name
