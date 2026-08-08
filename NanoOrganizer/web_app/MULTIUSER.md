# Access modes and multi-user mode

The web app has two independent choices:

- **access mode**: `admin` (for the owner), `user` (per-account folders), or
  `local` (the existing unrestricted local workflow); and
- **site**: `beamline`/`onsite` or `off_beamline`/`offsite`.

The preferred configuration is the machine-local `~/.config/pyViz.conf` file.
Copy [`.config/pyViz.conf.example`](../../.config/pyViz.conf.example) and set
`NANOORGANIZER_CONFIG` only when the file lives somewhere else. A project-local
`.config/pyViz.conf` is also discovered automatically. Real config files are
ignored by Git because they contain local paths and password hashes.

The legacy JSON store remains supported through `NANOORGANIZER_USERS_FILE`.
When both are present, the explicit JSON file wins for duplicate usernames.

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

## INI configuration

The equivalent configuration for the owner and the current off-beamline
machine looks like this:

```ini
[application]
access_mode = admin
site = off_beamline
beamline = smi
start_dir = /home/user/Facility_Link/beamline_a_remote/2026-2/pass-000000/projects/microbeam_Kim/Results

[paths]
off_beamline = /home/user/Facility_Link/{beamline}_remote
on_beamline = /facility/data1/{beamline}/proposals

[admin]
username = yuzhang
password_hash = <sha256-hex>
all_paths = true

[user.alice]
password_hash = <sha256-hex>
paths = /data/alice
off_beamline_paths = /data/alice/beamline_copy
```

`all_paths = true` gives the administrator every path readable by the server
process. A normal user receives only `paths` plus the optional site-specific
paths. The compact mapping form is also supported:

```ini
[users]
alice = /data/alice, /data/shared
```

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

## Switching beamline/off-beamline data

The sidebar data-location selector follows `site` from `pyViz.conf` and can be
changed per page. `beamline_paths` keeps the relative cycle/proposal/project
suffix while replacing the site root. For the current off-beamline SMI mount,
the path below is therefore a valid starting folder:

```text
/home/user/Facility_Link/beamline_a_remote/2026-2/pass-000000/projects/microbeam_Kim/Results
```

The older `/mnt/data/FacilityData/...` and `~/FacilityData_Link/...` spellings
remain recognized as equivalent mounts.

## Scattering product selection

The GISAXS/GIWAXS and transmission explorers accept either a product root or a
specific product folder in their sidebar path box. They discover available
folders such as `cir_avg`, `qc`, `q_image`, and `qphi`, show the file count for
each, and render only the products selected by checkbox. The SAXS 1-D explorer
accepts the same root and automatically routes to its `cir_avg/` folder.
