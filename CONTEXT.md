# skill-loader

Domain language for the review gate. There is no `pending/` stage: run skill
status against a repository checkout, then activate named skills into `active/`.

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

**Skill status**:
The read-only review operation: content comparison of configured skills in
repository checkouts against active skills, including new / changed /
unchanged / missing, plus orphans. Never copies, links, or mutates active
skills. Does not report Git dirty state.
_Avoid_: fetch-skills, pending inspection, interactive approval prompt, Review
(as a command name)

**Activation**:
The single write that copies named skills from a repository checkout's working
tree into active skills and refreshes the matching agent-path links. This is
the approval; there is no separate approve-then-link phase. Requires explicit
skill names (no activate-all). A dirty checkout is allowed. Skipping is
denial; denial is not stored.
_Avoid_: install, publish, deploy, activate-all, approve-skills (as a second
write step before linking)

**Orphan**:
An active skill or managed agent-path link that no longer corresponds to a
manifest entry. Left in place; skill status reports orphans, but no removal
command is in scope yet.
_Avoid_: stale skill, unused skill, dangling install
