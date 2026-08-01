# skill-loader

`skill-loader` imports agent skills from selected Git repositories through a small,
review-first pipeline:

```text
config.toml → repos/ → active/ → agent skill directories
                  clone/pull  activate   symlink
```

Nothing from an external repository becomes available to an agent until it has
been reviewed in the repository checkout and explicitly activated into
`active/`. Agent paths only ever symlink into `active/`, never into `repos/`.
Repository checkouts and active skills are local state and are ignored by Git.

There is no `pending/` stage. After sync, compare configured skills in `repos/`
against `active/`, then activate named skills you approve.

## Requirements

`bin/sync-repos` requires Git and Python 3.11 or later. TOML parsing uses
Python's standard-library `tomllib` module, so no Python packages need to be
installed.

Use `bin/sync-repos --dry-run` to validate configured local checkouts and see
the planned clone or fast-forward operations without changing them.

## Workflow

1. Copy `config.toml.example` to `config.toml`, then add the repositories and
   skills to import.
2. Run `bin/sync-repos` to clone missing repositories into `repos/`, or pull
   existing ones.
3. Run `bin/skill-status` to compare each configured skill in the checkout
   against its active snapshot (new / changed / unchanged / missing), and to
   report orphans.
4. Inspect every changed or new skill in `repos/`, including referenced
   scripts and files.
5. Run `bin/activate-skills` with explicit skill names to copy those skills
   into `active/` and create the configured agent symlinks.

The commands are deliberately separate. Skill status never activates a skill,
and activation must never sync, pull, or execute code from a source repo.
Skipping activation is denial; denial is not stored.

## Manifest

Keep the configuration at `config.toml` in the project root. Define agent paths
first, then repositories. Repository names determine the directory below
`repos/`; skill names determine the directories below `active/`.

```toml
[agent_paths]
paths = ["./agents/skills", "./.claude/skills"]

[[repository]]
name = "example-skills"
url = "https://github.com/example/agent-skills.git"
branch = "main"
skills = [
  { name = "release-checklist", path = "skills/release-checklist" },
]

[[repository]]
name = "team-skills"
url = "https://github.com/example/team-skills.git"
branch = "main"
skills = [
  { name = "incident-response", path = "skills/incident-response" },
]
```

`path` is relative to its repository root and must name a skill directory
(containing `SKILL.md`). `agent_paths.paths` lists the directories where agents
discover skills. The loader creates one symlink per active skill at
`<agent path>/<skill name>`.

Agent paths may be absolute or relative to `config.toml`. Do not use `~` or
environment-variable expansion. Repository skill paths must not escape their
repository.

## Command contracts

The implementation should provide these executable commands under `bin/`:

| Command | Allowed changes | Required behaviour |
| --- | --- | --- |
| `bin/sync-repos` | `repos/` | Clone a missing configured repository; otherwise fast-forward its configured branch. Refuse a dirty checkout, a URL mismatch, or a non-fast-forward update. |
| `bin/skill-status` | none (read-only) | Compare each configured skill's checkout path to its active snapshot. Report new / changed / unchanged / missing, plus orphans. Never write `active/` or agent links. |
| `bin/activate-skills` | `active/`, configured agent skill directories | Copy explicitly named skills from the repository checkout working tree into `active/`, then create or replace only the corresponding configured symlinks into `active/`. Never bulk-activate every diff. Dirty checkouts are allowed. |

Each command should fail before making partial changes whenever its inputs can
be validated up front. Activation must use a recoverable swap or rollback
strategy so a failed link update does not leave `active/` and agent directories
out of sync. No command should delete a skill, checkout, or symlink that the
manifest does not own. Orphans (active skills or managed links with no
manifest entry) are reported by skill status and left in place until an
explicit removal command exists.

## Review checklist

Treat repository checkouts as untrusted source code. Before activation, review:

- `SKILL.md`, all linked Markdown, and agent metadata;
- shell scripts, package manifests, hooks, and executable files;
- external URLs, network access, credential references, and destructive
  commands; and
- unexpected symlinks or files outside the declared skill directory.

Use `bin/skill-status` to compare the checkout with the previously activated
version when updating an existing skill. The human approval decision remains
outside skill status: activation with explicit skill names is the only approve
step.

## Local directories

```text
config.toml.example # tracked configuration template
config.toml         # local configuration
repos/              # ignored Git checkouts (review surface)
active/             # ignored, approved skill snapshots
bin/                # tracked command entry points
```

`config.toml`, `repos/`, and `active/` must be listed in `.gitignore`. Keep
`config.toml.example` tracked so the expected configuration remains
reviewable.

Domain language for these concepts lives in `CONTEXT.md`.
