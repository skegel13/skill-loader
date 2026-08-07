# Manifest and path rules

`config.toml` is the only source of desired agent paths, repositories, and
skills. Agent paths live in `agent_paths.paths`; skills are modelled in each
repository's `skills` array. Never infer configuration from the filesystem.

## Reject early

These are errors, caught during parsing rather than mid-write:

- Duplicate repository or skill names.
- Repository skill paths that are absolute or escape the repository.
- A skill directory with no `SKILL.md`.
- Agent skill paths using environment-variable expansion (`$` or `%`).
- A `~` anywhere but the start of an agent path.

## Resolution

- A leading `~` or `~/...` in an agent path expands to the home directory.
- Relative agent skill paths resolve from the directory containing
  `config.toml`.
- A source symlink that resolves outside its declared skill directory is not
  followed.
