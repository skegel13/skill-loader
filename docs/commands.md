# Command contracts

The two commands stay independent: `bin/sync-repos` owns Git checkout state,
`bin/sync-skills` owns review, promotion, symlinks, and orphan cleanup.

Shared manifest parsing, path validation, and filesystem operations live in
`skill_loader/` with unit tests. Both commands print the repository, skill, and
target they are about to change, and exit non-zero on any unsafe or incomplete
operation.

## bin/sync-repos

- Clones or fast-forward-pulls configured repositories. Nothing else: no reset,
  clean, rebase, force-pull, or modification of a dirty checkout.
- Provides a dry-run mode.

## bin/sync-skills

The only writer of `active/` and of agent skill directories.

- Shows a full diff for every new or changed configured skill and copies only
  the ones explicitly confirmed, from the checkout working tree. Dirty
  checkouts are allowed.
- Writes only to paths the manifest owns, plus confirmed orphans (below).
- Creates symlinks that point into `active/` and nowhere else.
- A rejection leaves the existing active snapshot untouched and is not
  recorded; there is no durable denial.

Orphan removal needs its own explicit confirmation and is limited to the orphan
active skill plus its matching symlinks in currently configured agent paths.
Everything else in those directories is unmanaged and must be preserved.

`--dry-run` shows the same reviews without prompting or touching any runtime
path, including the agent links it would create.
