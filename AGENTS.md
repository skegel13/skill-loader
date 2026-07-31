# Contributing to skill-loader

This project is a review gate for third-party agent skills. Preserve the
pipeline and its trust boundaries:

```text
external repository → repos/ → pending/ → active/ → agent symlink
       untrusted       untrusted  approved     available to an agent
```

## Invariants

- `manifest.toml` is the only source of desired repositories, skills, and agent
  destinations. Do not infer configuration from the filesystem.
- `repos/`, `pending/`, and `active/` are ignored runtime state. Never commit
  their contents.
- Synchronization only clones or fast-forward-pulls configured repositories.
  It must not reset, clean, rebase, force-pull, or modify a dirty checkout.
- Fetching copies declared skill directories into `pending/`; it does not write
  `active/`, create agent links, execute imported files, or install packages.
- Activation is the only operation that writes `active/` or agent skill
  directories. It may touch only paths owned by the manifest and must only
  create symlinks that point into `active/`.
- Reject malformed input early: duplicate names, unknown repositories, absolute
  or escaping skill paths, missing `SKILL.md`, and target directories outside
  an explicit absolute `skills_path` are errors.
- Do not follow a source symlink that resolves outside its declared skill
  directory. Preserve or reject internal symlinks intentionally; never copy a
  link as an unchecked escape hatch.

## Implementation shape

Keep the three commands independent and small:

1. `bin/sync-repos` owns Git checkout state.
2. `bin/fetch-skills` owns pending snapshots.
3. `bin/activate-skills` owns promotion and agent symlinks.

Put shared manifest parsing, path validation, and filesystem operations in a
small library with unit tests. Commands should print the repository, skill, and
target they are about to change, provide a dry-run mode, and exit non-zero on
any unsafe or incomplete operation.

When an operation changes multiple destinations, validate all inputs first,
then use staging directories and atomic renames where the platform permits.
If a later operation fails, restore the prior managed state. Never remove an
unmanaged file or symlink merely because it conflicts with a requested skill;
report the conflict and require the user to resolve it.

## Tests

Cover at least these behaviours before changing the command implementation:

- clone versus clean fast-forward pull, and refusal of dirty or divergent
  repositories;
- manifest validation and path traversal rejection;
- a fetch that never changes active skills or agent directories;
- rejection of source symlinks escaping the skill root;
- activation creates correct relative or absolute links into `active/`;
- a conflicting unmanaged target is preserved; and
- failures during activation leave prior active skills and managed links usable.

Treat imported skill contents as test fixtures, never executable setup steps.
