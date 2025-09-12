# Releases and Updates

This project uses SemVer tags (vX.Y.Z) to mark stable releases. Devices can switch releases by checking out a tag and reapplying config.

Authoring a release (controller)
- Update VERSION file: edit `VERSION` to the new version (e.g., `1.2.3`).
- Commit changes: `git commit -am "chore: release v$(cat VERSION)"`.
- Create annotated tag:
  - Unsigned: `git tag -a v$(cat VERSION) -m "release v$(cat VERSION)"`
  - Signed (optional): `git tag -s v$(cat VERSION) -m "release v$(cat VERSION)"`
- Push branch and tag: `git push origin HEAD --tags`

Updating a device
- From the repo directory `/opt/airplay_wyse`:
  - Select a specific tag: `./bin/select-tag v1.2.3`
  - Or select latest SemVer tag: `./bin/select-tag --latest`
  - Apply configuration: `sudo ./bin/apply` (if you changed name or ALSA, pass flags)

Notes
- `bin/select-tag` runs as an unprivileged user; it does not write configs.
- `bin/apply` requires root to write `/etc/shairport-sync.conf` and restart the service.
- If you prefer signed tags, distribute the maintainer’s public key and verify signatures out-of-band.

