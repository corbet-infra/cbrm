# Contributing

The primary repository is [forge.corbet.ch/corbet-infra/cbrm](https://forge.corbet.ch/corbet-infra/cbrm); please open
issues and pull requests there. GitHub, GitLab and Bitbucket carry read-only mirrors.

## Development

```sh
nix develop          # Python with all dependencies, pytest, ruff
pytest               # unit tests, no network
ruff check .         # lint; the rules are in pyproject.toml
nix build            # the package; runs the tests
```

Without Nix: `uv run --with pytest pytest` and `uvx ruff check .`.

```
src/cbrm/
  panel.py        Panel      login, session, server-rendered pages, panel JSON endpoints, file downloads
  livewire.py     Page/Component  Livewire calls with contract checks (methods, models, endpoints)
  console.py      Console    the VNC console: Proxmox noVNC websocket <-> local TCP <-> vncdotool
  features/       REGISTRY   every operation: name, risk, summary, help, parameters, run, verify, check
  service.py      Service    the rules: allow-list, confirmations, dry run, audit log, verification, doctor
  cli.py api.py mcp.py       the three interfaces, generated from the registry
  client.py       the Service interface over the HTTP API (CBRM_API_URL)
tests/            pytest; tests/fixtures holds anonymised panel renderings
skills/bero/      the agent skill
docs/             architecture, operations, and the generated command reference
scripts/          command_reference.py writes docs/command-reference.md
```

[docs/architecture.md](docs/architecture.md) explains the layers and the panel mechanisms;
[docs/operations.md](docs/operations.md) covers running the API and releasing.

## Adding a feature

1. One `@feature(name, risk, summary, help, params, verify=…, check=…)` in `src/cbrm/features/`. The risk class is
   `read`, `secret`, `change` or `destroy`; there is no class for spending money, and none will be added. The
   summary is a short line, verb first, at most 10 words; the help is the full, precise text. Account-wide features
   are named `account-…`; the name gives their scope, so the help does not repeat it.
2. Read and check first: `Component.require(...)` for every Livewire method and model the request relies on,
   `Page.require_endpoint(...)` / `common.require_post(...)` for the page's own scripts. If the panel looks different,
   raise `ContractError`; never guess.
3. Hand the one changing request to `ctx.send(description, fn)`: a dry run returns the description instead.
4. `verify(ctx, vm, result, **args)` re-reads the panel (`ctx.fresh(vm)`) and returns `True`, `False` or `None`;
   wrap it in `@tolerant` so a hiccup while re-reading becomes `None`.
5. `check(ctx, vm)` proves read-only that the panel still offers what the feature needs (`cbrm doctor`).
6. Tests against a fixture, add the feature to `AREAS` in `scripts/command_reference.py`, and run
   `python scripts/command_reference.py`; `tests/test_docs.py` fails while the reference is out of date. The wiki's
   Command reference page is a copy of `docs/command-reference.md`.

CLI, HTTP API and MCP pick the feature up automatically, with the confirmations of its risk class.

## Fixtures and recording the panel

Tests never touch the network: the panel is a fake that serves files from `tests/fixtures` (see
`tests/test_service.py`). A fixture is a reduced rendering of a real panel page or component, recorded read-only and
anonymised: VM 1 / product 2, servers 9001…, names under `example.test`, documentation IP ranges, zero UUIDs, `TOKEN`
for CSRF tokens. `test_fixtures_hold_no_account_data` rejects fixtures with real names, addresses or e-mail
addresses. States the panel did not show while it was recorded are derived from a recording by the smallest change,
and the test says so.

Recording only reads: log in, GET the pages, and load lazy components the way the page does (`__lazyLoad`). Never
submit a form or call a Livewire method that changes something to find out how it works. A control the panel has
never shown is not implemented: cbrm does not send what it has not seen.

## Ground rules

- Results keep only what a feature chose to return (`common.panel_answer` keeps the panel's `state` and `message`):
  they end up in audit logs and in agents' context.
- Be kind to the provider: no polling loops, no parallel request storms, one session. cbrm makes the requests a
  person would make.
- English in code, comments and documentation. Commit messages in the imperative mood, one logical change per commit.
