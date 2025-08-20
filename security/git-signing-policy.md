# Signed Tag Policy

- Devices verify that the current checkout is an annotated, signed tag.
- Only verified tags are considered deployable. Unsigned or unverifiable refs cause converge to exit with code 5.
- Trusted GPG public keys are provisioned out-of-band on devices (see `security/keys/README.md`).
- Release process creates a signed annotated tag `vX.Y.Z` matching the `VERSION` file.
Devices require your GPG public key installed locally for `git verify-tag`.

- Release tags must be annotated and signed.
- On-device verification uses `git verify-tag` and therefore needs the signer’s public key in the local keyring.
- Install the key via `gpg --import maintainer.pub` as part of provisioning.
