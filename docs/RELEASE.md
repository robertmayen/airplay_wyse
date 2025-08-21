# Release Policy

- Never rewrite/retcon a published tag. If a release needs fixes, create a new SemVer tag (e.g., bump from `v0.2.0` to `v0.2.1`).
- Push new tags normally: `git tag -s vX.Y.Z && git push --tags`.
- Devices fetch with pruning (`git fetch --tags --force --prune --prune-tags`) to track the remote state and drop stale or moved tags.
- If you enable tag verification on devices, ensure tags are signed by a trusted key and available for `git verify-tag`.

Rationale: Immutable tags keep rollback/forward behavior predictable across all devices and avoid “tag moved” ambiguity during updates.

