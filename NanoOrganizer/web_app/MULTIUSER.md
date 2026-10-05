# Access modes and multi-user mode

None of this is needed on a single-user workstation. With no configuration file
the app runs in **`local`** mode: no login, and it browses whatever the account
running it can read. Configure the rest only when several people share one
server.

## The three access modes

| mode | login | may browse |
|---|---|---|
| `local` | none | everything the server process can read |
| `user` | required | each account's own `roots`, plus any shared `extra_roots` |
| `admin` | required | everything the server process can read |

The mode is set in the configuration file, or overridden by the
`NANOORGANIZER_MODE` environment variable.

## The configuration file

`~/.config/pyViz.conf` by default. Set `NANOORGANIZER_CONFIG` to use another
path; a project-local `.config/pyViz.conf` is also discovered automatically.
Copy [`.config/pyViz.conf.example`](../../.config/pyViz.conf.example) to start.

**Real configuration files are git-ignored and should stay that way** — they
contain local filesystem paths and password hashes. `viz-adduser` writes them
`chmod 600`.

```ini
[application]
access_mode = user
start_dir = /data/projects

[paths]
extra_roots =
    /data/shared

[admin]
username = owner
password_hash = <sha256-hex>
all_paths = true

[users]
alice = user
bob = user

[user:alice]
password_hash = <sha256-hex>
roots =
    /data/projects/alice
    /scratch/{username}
```

- **`password_hash`** — SHA-256 hex digest. Never a plaintext password.
- **`all_paths`** — grants everything the server process can read; `roots` is
  then ignored.
- **`roots`** — folders this account may browse, subfolders included. A
  non-admin with no roots gets no filesystem access at all. A leading `~`
  expands, and `{username}` becomes the account name.
- Usernames are matched case-insensitively.
- `[users]` says who exists and whether they are privileged; `[user:<name>]`
  carries that account's credentials and roots. Either may appear alone.

A legacy JSON user store is still read when `NANOORGANIZER_USERS_FILE` is set.
Where both exist, the JSON file wins for duplicate usernames.

## Managing users

```bash
viz-adduser /path/to/users.json owner --admin
viz-adduser /path/to/users.json alice --root /data/projects/alice
```

The password is prompted for, never echoed, and only its hash is written. Run
it again with the same username to update an account. The file is created on
first use and merged afterwards.

## Launching

```bash
export NANOORGANIZER_USERS_FILE=/path/to/users.json
viz 5646
```

Every visitor gets a username and password form. The restriction is enforced in
one place and applies everywhere a path can be chosen — the sidebar folder
picker, the "Browse server" option in the plotting tools, and the Data Manager's
project create and load actions.

## What this is *not* for

Mapping one dataset onto different mount points on different machines is **not**
configured here. That is a project's path aliases
(`NanoOrganizer.core.pathmap.PathResolver`), and they travel with the project
rather than with the machine — see [`docs/sample_model.md`](../../docs/sample_model.md).
