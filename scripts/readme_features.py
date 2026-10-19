"""Regenerate the feature table in README.md from the registry: `python scripts/readme_features.py`."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from cbrm.features import REGISTRY

ORDER = {"read": 0, "secret": 1, "change": 2, "destroy": 3}
rows = ["| Feature | Risk | Arguments | What it does |", "|---|---|---|---|"]
for f in sorted(REGISTRY.values(), key=lambda f: (ORDER[f.risk], f.name)):
    args = [f"`--{p.name.replace('_', '-')}{' …' if p.multiple else ''}`" + ("" if p.required else "?") for p in f.params]
    if f.returns == "png":
        args.append("`--out`")
    rows.append(f"| `{f.name}` | {f.risk} | {' '.join(args) or '–'} | {f.help} |")
readme = Path(__file__).parents[1] / "README.md"
text = readme.read_text()
begin = "<!-- features:begin (generated from the registry; tests/test_docs.py keeps it complete) -->"
new = re.sub(re.escape(begin) + r".*?<!-- features:end -->", lambda _: begin + "\n" + "\n".join(rows) + "\n<!-- features:end -->",
             text, flags=re.S)
readme.write_text(new)
print(f"{len(REGISTRY)} features")
