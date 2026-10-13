# Security

Please report vulnerabilities privately: open a confidential issue on
[git.corbet.ch/corbet-infra/cbrm](https://git.corbet.ch/corbet-infra/cbrm/issues) or mail the
maintainer listed there. Do not file them on the mirrors.

Design notes:

- The panel password is read from the environment or a command, kept in memory, never logged and
  never passed as a process argument. The session cookie is stored with mode 0600.
- `cbrm serve` requires a bearer token on every route (constant-time comparison) and listens on
  loopback by default.
- Changing operations require the target to be repeated and are audit-logged.
- Console sessions use one-time tickets issued by the panel; cbrm does not store them.
