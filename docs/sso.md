# SSO integration

This project does not implement its own user database.

Recommended production setup:

```text
browser
  ↓
authentik
  ↓
reverse proxy
  ↓
X-authentik-username
  ↓
knowledge-admin
```

The admin service maps the authenticated username to:

```text
/host_home/<username>/knowledge
```

## Header

Default header:

```text
X-authentik-username
```

Config:

```yaml
admin:
  username_header: x-authentik-username
  allow_header_auth: true
```

## Security notes

- Do not expose knowledge-admin directly to the Internet.
- Only trust headers from your reverse proxy.
- Do not accept arbitrary path input from users.
- Always derive the knowledge root from the authenticated username.
