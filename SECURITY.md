# Security

Please report vulnerabilities privately: open a confidential issue on
[forge.corbet.ch/corbet-infra/cbrm](https://forge.corbet.ch/corbet-infra/cbrm/issues) or mail the
maintainer listed there. Do not file them on the mirrors.

Design notes:

- The panel password is read from the environment or a command, kept in memory, never logged and
  never passed as a process argument. The session cookie is stored with mode 0600.
- `cbrm serve` requires a bearer token on every route, the schema included (constant-time comparison);
  the framework's own documentation routes are switched off; it listens on loopback by default.
- A dry run never reveals a secret and sends nothing that changes or submits anything. Typed console
  text and passwords never reach the audit log.
- Changing operations require the target to be repeated and are audit-logged.
- Console sessions use one-time tickets issued by the panel; cbrm does not store them.
