# Filesystem safety

When an operation changes multiple destinations, validate every input before
writing anything, then stage the work in a temporary directory and move it into
place with atomic renames.

If a later step fails, restore the prior managed state so a partial run never
leaves a half-promoted skill behind.

A conflicting unmanaged file or symlink at a destination is not something to
resolve automatically. Report the conflict and stop; the user resolves it.
