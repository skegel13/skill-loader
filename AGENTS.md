# Contributing to skill-loader

This project is a review gate for third-party agent skills. Preserve the
pipeline and its trust boundaries:

```text
external repository → repos/ → active/ → agent symlink
       untrusted       untrusted approved  available to an agent
```

The repository checkout is the review surface (no `pending/` stage). Only
explicitly approved skills are copied into `active/`; agent symlinks may point
only there.

## Invariants

- `config.toml` is the only source of desired agent paths, repositories, and
  skills. Agent paths are in `agent_paths.paths`; do not infer configuration
  from the filesystem. Model skills in each repository's `skills` array.
- `repos/` and `active/` are ignored runtime state. Never commit their
  contents.
- `bin/sync-repos` only clones or fast-forward-pulls configured repositories.
  It must not reset, clean, rebase, force-pull, or modify a dirty checkout, and
  it never mutates `active/`.
- `bin/sync-skills` is the only writer of `active/` and agent skill directories.
  It shows a full diff for every new or changed configured skill, copies only
  explicitly confirmed skills from the checkout working tree (dirty checkouts
  allowed), may touch only paths owned by the manifest, and must only create
  symlinks that point into `active/`. It does not execute imported files or
  install packages. A rejection leaves the existing active snapshot untouched
  and is not recorded. Orphans may be removed only after explicit confirmation,
  and only the orphan active skill plus matching symlinks in currently
  configured agent paths; preserve all unmanaged files and links.
- Reject malformed input early: duplicate repository or skill names, absolute
  or escaping repository skill paths, missing `SKILL.md`, and agent skill paths
  using environment-variable expansion (`$` or `%`) are errors. Leading `~` /
  `~/...` in agent paths expands to the home directory; mid-path `~` is an
  error. Resolve relative agent skill paths from the directory containing
  `config.toml`.
- Do not follow a source symlink that resolves outside its declared skill
  directory. Never copy a link as an unchecked escape hatch.

## Implementation shape

Keep the two commands independent:

1. `bin/sync-repos` owns Git checkout state.
2. `bin/sync-skills` owns comparison, interactive review, promotion into
   `active/`, agent symlinks, and confirmed orphan removal.

Put shared manifest parsing, path validation, and filesystem operations in a
small library with unit tests. Commands should print the repository, skill, and
target they are about to change, provide a dry-run mode, and exit non-zero on
any unsafe or incomplete operation.

When an operation changes multiple destinations, validate all inputs first,
then use staging directories and atomic renames where the platform permits.
If a later operation fails, restore the prior managed state. On a conflicting
unmanaged file or symlink, report the conflict and require the user to resolve
it.

## Tests

Cover every invariant above before changing command implementation. Treat
imported skill contents as test fixtures, never executable setup steps.
