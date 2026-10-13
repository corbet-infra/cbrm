"""The README's feature table lists every registered feature (it is generated from the registry)."""
from pathlib import Path

from cbrm.features import REGISTRY


def test_readme_lists_every_feature():
    readme = (Path(__file__).parents[1] / "README.md").read_text()
    table = readme.split("<!-- features:begin")[1].split("<!-- features:end")[0]
    missing = [n for n in REGISTRY if f"| `{n}` |" not in table]
    assert not missing, f"regenerate the README feature table; missing: {missing}"


def test_account_wide_features_are_documented_as_not_limited_by_the_allow_list():
    """The allow-list only decides which VM may name the account context; the docs, the skill and the features'
    own help must not let anyone believe it scopes `account-*` features."""
    root = Path(__file__).parents[1]
    phrase = "not limited by the VM allow-list"
    for doc in ("README.md", "skills/bero/SKILL.md", "docs/architecture.md"):
        assert phrase in (root / doc).read_text().replace("**", ""), doc
    for name in ("account-ssh-key-import", "account-ssh-key-delete"):
        assert phrase in REGISTRY[name].help


def test_readme_table_shows_every_features_risk_class():
    """Regenerated after a risk class changed (task-create became destroying): `python scripts/readme_features.py`."""
    readme = (Path(__file__).parents[1] / "README.md").read_text()
    table = readme.split("<!-- features:begin")[1].split("<!-- features:end")[0]
    wrong = [n for n, f in REGISTRY.items() if f"| `{n}` | {f.risk} |" not in table]
    assert not wrong, f"regenerate the README feature table; wrong risk class for: {wrong}"
