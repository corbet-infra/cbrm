"""The README's feature table lists every registered feature (it is generated from the registry)."""
from pathlib import Path

from cbrm.features import REGISTRY


def test_readme_lists_every_feature():
    readme = (Path(__file__).parents[1] / "README.md").read_text()
    table = readme.split("<!-- features:begin")[1].split("<!-- features:end")[0]
    missing = [n for n in REGISTRY if f"| `{n}` |" not in table]
    assert not missing, f"regenerate the README feature table; missing: {missing}"
