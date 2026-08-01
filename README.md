# skill-loader

`skill-loader` imports agent skills from selected Git repositories through a small,
review-first pipeline:

```text
config.toml → repos/ → pending/ → active/ → agent skill directories
                  clone/pull  copy     approve    symlink
```

Nothing from an external repository becomes available to an agent until it has
been reviewed in `pending/` and explicitly activated. The repository cache,
staging area, and activated skills are local state and are ignored by Git.

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
3. Run `bin/fetch-skills` to copy the selected skill directories to `pending/`.
4. Inspect every pending change, including referenced scripts and files.
5. Run `bin/activate-skills` to replace the matching entries in `active/` and
   create the configured agent symlinks.

The commands are deliberately separate. Fetching must never activate a skill,
and activation must never fetch, pull, or execute code from a source repo.

## Manifest

Keep the configuration at `config.toml` in the project root. Define agent paths
first, then repositories. Repository names determine the directory below
`repos/`; skill names determine the directories below `pending/` and `active/`.

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
| `bin/fetch-skills` | `pending/` | Validate every configured source path, then copy each complete skill directory into a fresh pending snapshot. Never follow links that leave the source skill directory. |
| `bin/activate-skills` | `active/`, configured agent skill directories | Validate the pending snapshot, promote the selected skills to `active/`, then create or replace only the corresponding configured symlinks. |

Each command should fail before making partial changes whenever its inputs can
be validated up front. Activation must use a recoverable swap or rollback
strategy so a failed link update does not leave `active/` and agent directories
out of sync. No command should delete a skill, checkout, or symlink that the
manifest does not own.

## Review checklist

Treat pending skills as untrusted source code. Before activation, review:

- `SKILL.md`, all linked Markdown, and agent metadata;
- shell scripts, package manifests, hooks, and executable files;
- external URLs, network access, credential references, and destructive
  commands; and
- unexpected symlinks or files outside the declared skill directory.

Compare `pending/` with the previously activated version when updating an
existing skill. The tool should make that comparison convenient, but the human
approval decision remains outside the fetch step.

## Local directories

```text
config.toml.example # tracked configuration template
config.toml         # local configuration
repos/         # ignored Git checkouts
pending/       # ignored, untrusted skill snapshots
active/        # ignored, approved skill snapshots
bin/           # tracked command entry points
```

`config.toml`, `repos/`, `pending/`, and `active/` must be listed in
`.gitignore` when the commands are implemented. Keep `config.toml.example`
tracked so the expected configuration remains reviewable.
