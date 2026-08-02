# Use skill status as the interactive promotion gate

`bin/sync-skills` replaces the separate read-only status and activation steps.
After `sync-repos`, it shows a full diff for each new or changed configured
skill and immediately promotes only individually approved skills. Rejections
are no-ops, not durable decisions. This keeps review and the promoted bytes in
one user-facing operation without adding a pending tree or approval manifest;
the command also offers explicit, narrowly scoped orphan cleanup after review.
