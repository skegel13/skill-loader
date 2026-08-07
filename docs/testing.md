# Testing

`python3 -m unittest discover -s tests -t .`

Cover the invariants in [command contracts](commands.md),
[manifest rules](manifest.md), and [filesystem safety](filesystem-safety.md)
before changing a command's implementation.

Imported skill content is a test fixture — write it as inert files, never as an
executable setup step.
