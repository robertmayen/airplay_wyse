# Signed Tag Policy

- Tag verification on devices is optional and can be enabled per host (inventory `verify_gpg: true`) or via `AIRPLAY_VERIFY_TAGS=1`.
- When enabled, converge/updater require the current checkout to be an annotated, signed tag; verification failures exit with code 5.
- Trusted GPG public keys should be provisioned out-of-band on devices (see `security/keys/README.md`).
- Release process should create annotated, signed tags `vX.Y.Z` matching the `VERSION` file.

Release discipline
- Never rewrite/retcon a published tag. For fixes, create a new SemVer tag (e.g., bump `v0.2.0` → `v0.2.1`).
- Devices fetch tags with pruning (`git fetch --tags --force --prune --prune-tags`) to synchronize remote tag state and drop stale/moved tags.
