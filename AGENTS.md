# Contributing to skill-loader

This project is a review gate for third-party agent skills. Preserve the
pipeline and its trust boundaries:

```text
external repository → repos/ → active/ → agent symlink
       untrusted       untrusted approved  available to an agent
```

There is no `pending/` stage. The repository checkout is the review surface;
skill status copies explicitly approved skills into `active/`. Agent symlinks
may point only into `active/`.

## Invariants

- `config.toml` is the only source of desired agent paths, repositories, and
  skills. Agent paths are in `agent_paths.paths`; do not infer configuration
  from the filesystem.
- Model skills in each repository's `skills` array; skills belong to their
  source repository rather than being a separate top-level collection.
- `repos/` and `active/` are ignored runtime state. Never commit their
  contents.
- Synchronization only clones or fast-forward-pulls configured repositories.
  It must not reset, clean, rebase, force-pull, or modify a dirty checkout.
- Skill status is the interactive review gate: it shows a full diff for every
  new or changed configured skill and prompts to activate or reject it. It
  does not execute imported files or install packages. Rejected skills are not
  recorded; a rejected update leaves the existing active snapshot untouched.
- Skill status is the only operation that writes `active/` or agent skill
  directories. It copies only explicitly confirmed skills from the checkout
  working tree (dirty checkouts allowed), may touch only paths owned by the
  manifest, and must only create symlinks that point into `active/`.
- Sync never mutates `active/`. Skill status may offer to remove each orphan
  after review, but only after explicit confirmation. It may remove an orphan
  active skill and matching symlinks in currently configured agent paths; it
  must preserve all unmanaged files and links.
- Reject malformed input early: duplicate repository or skill names, absolute
  or escaping repository skill paths, missing `SKILL.md`, and agent skill paths
  using environment-variable expansion (`$` or `%`) are errors. Leading `~` /
  `~/...` in agent paths expands to the home directory; mid-path `~` is an
  error. Resolve relative agent skill paths from the directory containing
  `config.toml`.
- Do not follow a source symlink that resolves outside its declared skill
  directory. Preserve or reject internal symlinks intentionally; never copy a
  link as an unchecked escape hatch.

## Implementation shape

Keep the two commands independent and small:

1. `bin/sync-repos` owns Git checkout state.
2. `bin/skill-status` owns comparison, interactive review, promotion into
   `active/`, agent symlinks, and confirmed orphan removal.

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
- skill status that shows complete diffs and promotes only explicitly approved
  skills;
- rejection of source symlinks escaping the skill root;
- approved promotion from a checkout copies into `active/` and creates correct
  relative or absolute links into `active/`;
- rejected skills leave prior active snapshots and links usable, while approved
  skills may come from a dirty checkout;
- a conflicting unmanaged target is preserved;
- orphans are removed only after confirmation, without touching unmanaged
  files or links; and
- failures during promotion leave prior active skills and managed links usable.

Treat imported skill contents as test fixtures, never executable setup steps.
