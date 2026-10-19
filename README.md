# cbrm

[![PyPI](https://img.shields.io/pypi/v/cbrm)](https://pypi.org/project/cbrm/)
[![Python](https://img.shields.io/pypi/pyversions/cbrm)](https://pypi.org/project/cbrm/)
[![License: LGPL-3.0 with linking exception](https://img.shields.io/badge/license-LGPL--3.0%20%2B%20linking%20exception-blue)](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/LICENSE.md)

cbrm is a CLI, HTTP API and MCP server for the [BERO HOST](https://bero-host.de) customer panel, which has no API.
It covers the panel's KVM rootserver features: status, logs, VNC console, power, reinstall, ISOs, backups,
scheduled tasks, rDNS, firewalls, internal networks, support tickets and invoices. AI agents use it through the MCP
server and the [`bero` skill](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/skills/bero/SKILL.md).

```sh
uv tool install cbrm        # or: pipx install cbrm; Python 3.11+
```

```sh
export CBRM_CREDENTIALS_CMD="pass show hosting/bero-host"    # prints the panel user and password on two lines
cbrm vms
cbrm logs 10001 --n 5
cbrm console 10001 --out screen.png
cbrm power 10001 --action restart --confirm 10001
claude mcp add bero --env CBRM_CREDENTIALS_CMD="pass show hosting/bero-host" -- uvx --from cbrm cbrm-mcp
```

Safety:

- Every change needs the target repeated (`--confirm`), destructive ones twice; `--dry-run` shows the request without sending it.
- `CBRM_VMS` limits cbrm to the listed servers; `account-*` commands act on the whole account and are not limited by the VM allow-list.
- cbrm never spends money: renewals, upgrades and orders stay in the panel.

cbrm is independent and not affiliated with BERO HOST.

Documentation is in the [wiki](https://forge.corbet.ch/corbet-infra/cbrm/wiki):
[Installation and credentials](https://forge.corbet.ch/corbet-infra/cbrm/wiki/Installation-and-credentials),
[Usage](https://forge.corbet.ch/corbet-infra/cbrm/wiki/Usage),
[Safety model](https://forge.corbet.ch/corbet-infra/cbrm/wiki/Safety-model),
[Command reference](https://forge.corbet.ch/corbet-infra/cbrm/wiki/Command-reference).
Issues and pull requests go to [forge.corbet.ch/corbet-infra/cbrm](https://forge.corbet.ch/corbet-infra/cbrm);
GitHub, GitLab and Bitbucket are read-only mirrors. License: LGPL-3.0-only WITH LGPL-3.0-linking-exception
([LICENSE.md](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/LICENSE.md)).
