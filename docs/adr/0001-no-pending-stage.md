# No pending stage between repos and active

We dropped a separate `pending/` snapshot. Review happens on the live
repository checkout after sync; activation copies named skills into `active/`
and refreshes agent symlinks. A frozen pending tree would isolate review from
later syncs, but it duplicated the untrusted surface and added a fetch step
whose only job was to look like `repos/`. Accepting live-checkout review keeps
the trust gate (agents only see `active/`) with a simpler pipeline:
`sync-repos` → `skill-status` (review and activation).
