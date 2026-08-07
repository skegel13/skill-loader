# skill-loader

Domain language for the review gate. There is no `pending/` stage: run
`sync-skills` against a repository checkout, then activate named skills into
`active/`.

## Language

**Repository checkout**:
A local Git working tree of a configured external skill source. Untrusted; the
surface used for review after sync.
_Avoid_: pending, staging area, cache

**Skill**:
A named skill directory declared under a repository in the manifest.
Activation is per skill, never per repository or whole manifest.
_Avoid_: package, plugin, module

**Active skill**:
An approved filesystem snapshot under `active/` (name kept for now), keyed by
skill name. Sync never changes it.
_Avoid_: installed skill, published skill, deployed skill, approved/

**Agent path**:
A configured directory (`agent_paths.paths`) where an agent discovers skills.
It holds symlinks into `active/` only, never into repository checkouts.
_Avoid_: agent skills folder, install path

**Sync skills**:
The interactive review gate (`bin/sync-skills`): it compares configured skills
in repository checkouts against active skills, shows each new or changed
skill's diff, and lets the operator promote or skip that skill. It also reports
unchanged, missing, and orphaned skills. Does not report Git dirty state.
_Avoid_: skill status, fetch-skills, pending inspection

**Activation**:
The promotion that copies a reviewed skill from a repository checkout's
working tree into active skills and refreshes its matching agent-path links.
It follows an explicit confirmation during sync skills; there is no separate
approve-then-link phase. A dirty checkout is allowed. Skipping is denial;
denial is not stored.
_Avoid_: install, publish, deploy, approve-skills (as a separate step)

**Orphan**:
An active skill or managed agent-path link that no longer corresponds to a
manifest entry. Sync skills reports it and may remove it only after an
explicit confirmation; unrelated files and links are unmanaged and preserved.
_Avoid_: stale skill, unused skill, dangling install
