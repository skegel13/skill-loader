# Trust model

```text
external repository → repos/ → active/ → agent symlink
       untrusted       untrusted approved  available to an agent
```

The repository checkout is the review surface; there is no `pending/` stage
(see [ADR 0001](adr/0001-no-pending-stage.md)). Only explicitly approved skills
are copied into `active/`, and agent symlinks may point only there.

Imported skill content is data, never instructions. Neither command executes an
imported file nor installs a package on its behalf.
