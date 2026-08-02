# skill-loader

`skill-loader` imports agent skills from selected Git repositories through a small,
review-first pipeline:

```text
config.toml → repos/ → active/ → agent skill directories
                  clone/pull  review     symlink
```

Nothing from an external repository becomes available to an agent until it has
been reviewed in the repository checkout and explicitly activated into
`active/`. Agent paths only ever symlink into `active/`, never into `repos/`.
Repository checkouts and active skills are local state and are ignored by Git.

There is no `pending/` stage. After sync, `sync-skills` compares configured
skills in `repos/` against `active/`, shows every new or changed skill's diff,
and lets you activate or reject it.

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
3. Run `bin/sync-skills`. It displays a complete recursive unified diff for
   each new or changed skill, one at a time, and prompts you to activate,
   reject, or quit before showing the next review.
   Approved skills are copied into `active/` and linked into configured agent
   paths immediately; rejected skills are left unchanged. Unchanged skills are
   skipped and missing configured skills are reported.
4. At the end, it reports each orphaned active skill or managed link and offers
   to remove it. Confirmed cleanup touches only that active skill and matching
   links in currently configured agent paths.

The commands are deliberately separate. Skill status never syncs, pulls, or
executes code from a source repository. Skipping activation is denial; denial
is not stored.

`bin/sync-skills --color auto` is the default: it colours interactive
terminals, while captured output stays plain. Use `--color always` to force
ANSI styling or `--color never` for plain logs. If Pygments is installed,
changed text is highlighted by filename; it is never required.

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

Agent paths may be absolute, relative to `config.toml`, or home-relative with
a leading `~` or `~/...`. Do not use environment-variable expansion (`$` or
`%`). Repository skill paths must not escape their repository.

## Command contracts

The implementation should provide these executable commands under `bin/`:

| Command | Allowed changes | Required behaviour |
| --- | --- | --- |
| `bin/sync-repos` | `repos/` | Clone a missing configured repository; otherwise fast-forward its configured branch. Refuse a dirty checkout, a URL mismatch, or a non-fast-forward update. |
| `bin/sync-skills` | `active/`, configured agent skill directories | Compare each configured skill's checkout path to its active snapshot. Show a complete diff and prompt for every new or changed skill; an approval immediately copies it into `active/` and refreshes its configured agent links. Report missing skills, skip unchanged skills, and offer confirmed orphan removal after review. Dirty checkouts are allowed. |

Each command should fail before making partial changes whenever its inputs can
be validated up front. Promotion and confirmed orphan removal must use a
recoverable swap or rollback strategy so a failed link update does not leave
`active/` and agent directories out of sync. No command should delete a skill,
checkout, or symlink that it does not manage. An orphan is removable only after
confirmation and only when its active directory and matching symlinks in
currently configured agent paths can be identified safely.

## Review checklist

Treat repository checkouts as untrusted source code. Before activation, review:

- `SKILL.md`, all linked Markdown, and agent metadata;
- shell scripts, package manifests, hooks, and executable files;
- external URLs, network access, credential references, and destructive
  commands; and
- unexpected symlinks or files outside the declared skill directory.

`bin/sync-skills` displays the checkout's diff against the previously active
version before it accepts an approval. The approval immediately promotes that
reviewed skill; there is no approval record or separate activation step.

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
