# Contributing

Thank you for helping. The primary repository is
[git.corbet.ch/corbet-infra/cbrm](https://git.corbet.ch/corbet-infra/cbrm); please open issues and pull
requests there. GitHub, GitLab and Bitbucket carry read-only mirrors.

## Development

```sh
nix develop          # Python with all dependencies, pytest, ruff
pytest               # unit tests, no network
nix build            # the package; runs the tests
```

Without Nix: `python -m venv .venv && .venv/bin/pip install -e . pytest`.

## Ground rules

- **A new operation is one `@feature` in `cbrm/features/`** with its risk class (`read`, `secret`,
  `change`, `destroy`; there is no class for spending money, and none will be added), parameters, `run`,
  and where possible `verify` (re-read the effect) and `check` (read-only contract proof for `cbrm doctor`). CLI, API and MCP pick it up automatically; the
  service applies the confirmations. Run `python scripts/readme_features.py` to regenerate the README table.
- **Check before you send**: use `Component.require(...)` / `Page.require_endpoint(...)` for everything
  the request relies on, and hand the one changing request to `ctx.send(description, fn)`.
- **Never guess**: if the panel looks different from what you expect, raise `ContractError`.
- **Tests without network.** The panel is mocked (see `tests/test_service.py`). If you change a parser,
  add a fixture with the relevant (anonymised) HTML.
- Be kind to the provider: no polling loops, no parallel request storms. cbrm makes the requests a
  person would make.
- Commit messages in English, imperative mood; one logical change per commit.
