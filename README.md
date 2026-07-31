# skill-loader

`skill-loader` imports agent skills from selected Git repositories through a small,
review-first pipeline:

```text
manifest.toml → repos/ → pending/ → active/ → agent skill directories
                  clone/pull  copy     approve    symlink
```

Nothing from an external repository becomes available to an agent until it has
been reviewed in `pending/` and explicitly activated. The repository cache,
staging area, and activated skills are local state and are ignored by Git.

## Workflow

1. Add a repository and the skills to import to `manifest.toml`.
2. Run `bin/sync-repos` to clone missing repositories into `repos/`, or pull
   existing ones.
3. Run `bin/fetch-skills` to copy the selected skill directories to `pending/`.
4. Inspect every pending change, including referenced scripts and files.
5. Run `bin/activate-skills` to replace the matching entries in `active/` and
   create the configured agent symlinks.

The commands are deliberately separate. Fetching must never activate a skill,
and activation must never fetch, pull, or execute code from a source repo.

## Manifest

Keep the manifest at `manifest.toml` in the project root. Repository names are
local identifiers; they determine the directory below `repos/`. Skill names
are the identifiers used below `pending/` and `active/`.

```toml
[[repositories]]
name = "example-skills"
url = "https://github.com/example/agent-skills.git"
branch = "main"

[[skills]]
name = "release-checklist"
repository = "example-skills"
path = "skills/release-checklist"

[[agents]]
name = "codex"
skills_path = "/absolute/path/to/.codex/skills"

[[agents]]
name = "claude"
skills_path = "/absolute/path/to/.claude/skills"
```

`path` is relative to the configured repository root and must name a skill
directory (normally one containing `SKILL.md`). `skills_path` is the directory
where that agent discovers skills. The loader will create one symlink per
active skill at `<skills_path>/<skill name>`.

Use absolute paths for agent directories. Do not use `~`, environment-variable
expansion, or paths that escape a repository or skill directory: the loader
should treat these as invalid manifest values.

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
manifest.toml  # tracked configuration
repos/         # ignored Git checkouts
pending/       # ignored, untrusted skill snapshots
active/        # ignored, approved skill snapshots
bin/           # tracked command entry points
```

`repos/`, `pending/`, and `active/` must be listed in `.gitignore` when the
commands are implemented. Keep `manifest.toml` tracked so the imported skill
set is reproducible and reviewable.
