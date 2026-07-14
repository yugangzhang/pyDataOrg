# Multi-user mode

The web app supports per-user login with per-user folder access. It is enabled
by pointing the app at a JSON user store via the `NANOORGANIZER_USERS_FILE`
environment variable. When that variable is **unset**, the app keeps its old
behaviour (single shared password via `viz PORT PASSWORD`).

## User store schema

```json
{
  "yuzhang": { "password": "<sha256-hex>", "admin": true },
  "alice":   { "password": "<sha256-hex>",
               "roots": ["/mnt/data/FacilityData/.../alice_proposal"] }
}
```

- **`password`** — SHA-256 hex digest of the user's password (never plaintext).
- **`admin`** — optional. Admins can browse the entire filesystem; `roots` is
  ignored for them.
- **`roots`** — optional list of folders a non-admin user may browse (their
  subfolders are included automatically). A non-admin with no `roots` gets no
  filesystem access.
- Usernames are matched case-insensitively.

The file contains password hashes, so it is git-ignored (`users*.json`). Keep it
readable only by you (`chmod 600`, which `viz-adduser` sets automatically).

## Managing users

Use the `viz-adduser` helper (installed with the package). It prompts for the
password (never echoed) and writes the hash:

```bash
# Admin (full access):
viz-adduser /path/to/users.json yuzhang --admin

# Scoped user (one or more --root):
viz-adduser /path/to/users.json alice \
    --root /mnt/data/FacilityData/remote/beamline_b_remote/2026-2/pass-000000

# Update a user: just run it again with the same username.
```

The file is created on first use and merged on subsequent runs.

## Launching in multi-user mode

```bash
export NANOORGANIZER_USERS_FILE=/path/to/users.json
./run 5646          # no shared password needed; each user logs in
```

At startup every visitor sees a username + password form. After signing in they
can only browse their allowed folders; admins see everything. This is enforced
consistently across all tabs — the sidebar folder picker, the "Browse server"
option in the CSV/Image/Multi-Axes/3D tools, and the Data Manager project
create/load actions all honour the same restrictions.
