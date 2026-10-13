# Operating cbrm

## Credentials

Prefer `CBRM_CREDENTIALS_CMD` over the two plain variables: the password then stays in your secret
store and only exists in the process that needs it. cbrm never prints it and never passes it as a
command-line argument.

## Running the API for a team or for assistants

```sh
export CBRM_CREDENTIALS_CMD="pass show hosting/bero-host"
export CBRM_API_TOKEN="$(openssl rand -base64 32)"   # give this to the clients
export CBRM_VMS="10001 10002 10003"                  # optional allow-list
cbrm serve --host 127.0.0.1 --port 8765
```

Put a TLS reverse proxy in front if clients connect over a network, or keep it on loopback / a VPN.
Clients set `CBRM_API_URL` and `CBRM_API_TOKEN`; the panel password stays with the server.
The OpenAPI schema is at `GET /openapi.json` (with the token, like every route); load it into any OpenAPI viewer.

As a systemd service: run `cbrm serve` with `Environment=` / `EnvironmentFile=` for the variables
above, `StateDirectory=cbrm` and `Environment=XDG_STATE_HOME=%S`.

## State and audit

`$XDG_STATE_HOME/cbrm/` (default `~/.local/state/cbrm/`, mode 0700):

| File | Content |
|---|---|
| `cookies.json` | the panel session (0600); delete it to force a fresh login |
| `audit.log` | one line per changing request and its result, UTC |

## Checks before acting on a cluster member

cbrm acts on one server; it does not know your cluster. Before stopping or restarting a member, make
sure the others are healthy (quorum, replicas), and after a restart check that it came back — with
`cbrm console` if it waits at a boot or disk-unlock prompt.

## When the panel changes

BERO HOST can change its panel at any time. cbrm then fails loudly (`PanelError`, HTTP 502 from the
API) instead of guessing. To repair:

1. `cbrm --json status <vm>` and `cbrm logs <vm>` show which part broke.
2. Look at the page in a browser; compare with [architecture.md](architecture.md).
3. Fix the parser in `cbrm/panel.py`, add a test, release a patch version.

## Releasing

1. Update `CHANGELOG.md` and the version in `pyproject.toml`, `src/cbrm/__init__.py` and `flake.nix`.
2. `nix build` (runs the tests), commit, tag `vX.Y.Z` on the primary.
3. Build and upload to PyPI: `nix shell nixpkgs#python3Packages.build nixpkgs#twine -c sh -c 'python -m build && twine upload dist/*'`.
The mirrors follow the primary automatically.
