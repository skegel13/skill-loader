# skill-loader

A review gate that copies explicitly approved third-party agent skills out of
untrusted repository checkouts into `active/`, which agents reach by symlink.

- Python 3.11+ (`tomllib`), standard library only. No package manager, no
  dependencies.
- Tests: `python3 -m unittest discover -s tests -t .`
- `repos/` and `active/` are ignored runtime state. Never commit their
  contents.

Every change must preserve the trust boundary: agents read only from `active/`,
and only `bin/sync-skills` writes there.

## Guides

- [Trust model](docs/trust-model.md) — the pipeline and why each stage exists.
- [Command contracts](docs/commands.md) — what `bin/sync-repos` and
  `bin/sync-skills` may and may not do.
- [Manifest and path rules](docs/manifest.md) — `config.toml` parsing and the
  input it must reject.
- [Filesystem safety](docs/filesystem-safety.md) — multi-destination writes,
  rollback, and conflicts.
- [Testing](docs/testing.md) — what to cover before changing a command.
- [Domain language](CONTEXT.md) and [decision records](docs/adr/).
