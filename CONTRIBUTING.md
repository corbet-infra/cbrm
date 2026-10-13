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

- **Every interface goes through `cbrm.service.Service`.** New operations go there first, with their
  rule (allow-list, `confirm` for anything that changes a server, an audit line), then into the API,
  the client, the CLI and the MCP server.
- **Nothing destructive or costly**: no reinstall, restore, password or network reset, billing. If you
  need one of those, open an issue first.
- **Tests without network.** The panel is mocked (see `tests/test_service.py`). If you change a parser,
  add a fixture with the relevant (anonymised) HTML.
- Be kind to the provider: no polling loops, no parallel request storms. cbrm makes the requests a
  person would make.
- Commit messages in English, imperative mood; one logical change per commit.
