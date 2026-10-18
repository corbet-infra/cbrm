# Changelog

## Unreleased

New account-wide features (named `account-*`, not limited by the VM allow-list), all with a `doctor` check:

- Support tickets: `account-tickets` (search, pages), `account-ticket` (the whole thread), `account-ticket-create`
  (optionally linked to a VM, with attachments), `account-ticket-reply`, `account-ticket-close` (a closed ticket
  cannot be reopened). Attachments are read only from the directory named by `CBRM_ATTACH_DIR`.
- Internal networks: `account-networks` (id, title, description, subnet, servers, limit), `account-network-create`,
  `account-network-edit` (title, description), `account-network-server-add`, `account-network-server-remove`,
  and `account-network-delete` (destroy class: needs `confirm_destroy`). The add and delete methods are discovered in
  the network's rendering, because the panel shows those buttons only while they apply.
- Firewalls, read only: `account-firewalls` (list, limit, templates) and `account-firewall` (policies, rules, servers).
- Bookkeeping, read only: `account-invoices`, `account-orders`, `account-transactions` (search, pages).

## 0.4.2 — 2026-10-15

- Login works again: BERO HOST replaced the plain login form with a Livewire component (`auth.login`). cbrm
  now logs in through that component (fields `email` and `password`, method `login`) and counts the login as
  done only when the panel redirects away from `/login`. If the component's form changes, nothing is sent and
  the error is a contract error. 0.4.1 failed every command with "login form not found".
- cbrm never spends money (decision of 2026-10-13): the planned `cost` risk class is gone, together with
  `confirm_cost` in the library, `--confirm-cost` in the CLI, the HTTP API field and the MCP parameter.
  `feature()` raises `ValueError` for any risk class other than read, secret, change and destroy (it was an
  `assert`, which `python -O` skips). Renewals, upgrades and credit top-ups stay in the panel.

## 0.4.1 — 2026-10-13

Fixes from a second independent review (the 0.4.0 features):

- `account-ssh-key-delete` deletes only the key whose tile was shown: the id is parsed from the tile's own
  `selectSshKey(N)` button and must equal the tile's key id, and after selecting, the panel's `selectedKeyId`
  and `selectedKeyName` must both be the tile's; any mismatch is a contract error before `deleteSshKey` is sent.
  A key id that is not a number is a contract error, not a raw `ValueError`.
- `account-ssh-key-import`: the public key is parsed strictly (SSH wire format of each supported type, no
  trailing bytes, canonical base64, RSA of at least 2048 bits, at most 8 KiB, control characters refused in
  the comment; armor markers are refused only as such, a comment like `a-----b` is fine; non-ASCII key
  data no longer escapes as a `ValueError`). The Livewire state it writes to (`importSshKeyName`,
  `importSshKeyPublicKey`, `addSshKeyContentType`) is required before anything is sent.
- No more fake verification: `backup-create` re-reads the backups and is `verified: true` only when a new
  backup or one free slot less is listed (`false` if not, `null` if the panel cannot be read);
  `backup-restore` and `network-reset` no longer pass off the panel's own answer as verification
  (`verified: null`). An unknown verification stays `null` instead of being turned into `false`.
- `task-create` is now a **destroying** feature (both confirmations): the task acts later and repeatedly
  without you. A start in the past (panel time, Europe/Berlin) and a task identical to an existing one are
  refused; the dry run says the task repeats at the interval until it is deleted.
- A backup tile without exactly one id is a contract error (it used to become an id `null`); doctor's
  check of the backup features requires it.
- `network-reset` requires the two input fields the panel's script reads (`changeRootpasswordPassword`,
  `changeRootpasswordPasswordConfirmation`), sends exactly their values and refuses if they are missing or
  not empty.
- Panel answers: results (and so the audit log) keep only the panel's `state` and `message`. `renewal`
  returns the payment as amount and method name only (never an account identifier) and describes the
  upgrade section in its own words instead of returning component text. An unreadable remaining runtime
  or console port is a contract error; the command line prints one line, not a traceback, for content it did not expect
  (`CBRM_DEBUG=1` re-raises).
- `cbrm doctor` shares one context across its checks: the product page, the account page and every lazy
  component are loaded once.
- Documented: the `account-*` features act on the whole account and are **not limited by the VM allow-list**
  (README, skill, architecture, the features' help).
- `tzdata` is a dependency on Windows (the start of a task is checked against the panel's time zone).

## 0.4.0 — 2026-10-13

- New reads: `addresses`, `backups`, `automatic-backup-status`, `tasks`, `stats`, `stats-history`, `renewal`
  (runtime left, auto-renewal with the prices the panel quotes, upgrade possible or not, credit),
  `account-credit`, `account-ssh-keys`.
- New changes: `rdns-set`, `hostname-set`, `rename`, `backup-create`, `task-create`, `task-delete`,
  `account-ssh-key-import` (public keys only; a private key is refused), `account-ssh-key-delete`.
- New destroying features (two confirmations): `backup-delete`, `backup-restore`, `network-reset`.
- Account-wide features are named `account-*`; `<vm>` names the account context, so the allow-list and
  `--confirm <vm>` apply as before.
- Contract checks compare the field names of the page's own POSTs and the options of its forms (task
  actions and intervals) with what cbrm sends, before anything is sent.
- Not included on purpose: the paying actions (extend, upgrade, credit top-up) and backup file restore.

## 0.3.2 — 2026-10-13

Fixes from an independent review before the public announcement:

- A dry run of `root-password` revealed the password without confirmation; secret features now never run
  in a dry run, and a dry run returns only a description.
- `console-input` text and other secret arguments never reach the audit log; secret results are logged
  as their keys only.
- `iso-add` in a dry run no longer opens the form or sends the URL; its contract (form fields, method) is
  checked before anything is submitted.
- An error while verifying a change that was sent is reported as `verified: null` + `verify_error`, not as
  "nothing was sent"; the wording is now "the panel changed, so the change was not made".
- `doctor` respects the allow-list and reports instead of crashing.
- HTTP API: the framework's docs routes (which bypassed the token) are off; `/openapi.json` needs the
  token; a non-ASCII token is a 401, not a 500.
- Exact endpoint checks (`/stop` no longer matches `/stop-hard`); reinstall and set-root-password check the
  form fields they submit; drive and boot-order reads fail closed when the refresh is missing.
- Every HTTP error maps to `PanelError` (419 on an expired Livewire session included); the session's login
  and product scan are locked for the threaded API; the cookie file is written atomically and a damaged
  one is ignored.
- MCP tools run in a worker thread; the client reports a timeout as "may still be running".
- `console-input`: repeat x interval at most 120 s; the console cleans up when opening fails.

## 0.3.1 — 2026-10-13

- Fix: every command that used the console hung when the process exited (vncdotool's reactor thread
  was stopped too late). A regression test runs a process through it.
- Console: hard deadline per operation; the panel's noVNC proxy is retried while it starts;
  `console-input --repeat/--interval` to catch a boot menu.
- `drives` and `boot-order` read the hypervisor's live state (the panel caches both); `iso-mount` is
  verified only when exactly that file is in the drive (the panel reports success for an own ISO that is
  still downloading).
- New: `drive-delete`.
- README: absolute links (they work on PyPI), the ISO boot recipe, a status and roadmap section.

## 0.3.0 — 2026-10-13

- Architecture: a feature registry with risk classes (read, secret, change, destroy, cost); CLI, HTTP
  API and MCP tools are generated from it. Every changing feature takes `--dry-run`.
- Breaking safely: a generic Livewire layer checks components, methods, fields and endpoints before
  every change (`ContractError`, HTTP 409); changes are verified by re-reading the panel; `cbrm doctor`.
- New: CD drives, ISO list, insert/remove ISO, own ISO by URL, boot order, rescue system.
- CLI is now `cbrm <feature> <vm> --arg …` (e.g. `cbrm power <vm> --action restart --confirm <vm>`).

## 0.2.0 — 2026-10-13

- Reinstall from a template with stored SSH keys baked in (`reinstall`, double confirmation).
- Show, set or generate the root password (audited without the value).
- List installable templates and the account's stored SSH keys.
- Fix: an expired session made the next login fail (stale cookie shadowed the new one).

## 0.1.1 — 2026-10-13

- MCP server works with mcp 2.x (`MCPServer`) as well as 1.x (`FastMCP`); 0.1.0 failed to start with mcp 2.x.
- Test that the MCP server registers its tools.

## 0.1.0 — 2026-10-13

First version: status, action log, console screenshot and input, power — as a Python library, CLI,
HTTP API and MCP server, with an agent skill.
