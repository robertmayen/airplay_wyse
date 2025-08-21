# Packaging for GitOps Deployment

Attach Debian packages to a signed tag under `pkg/` to have devices install or upgrade them automatically during converge.

## Supported packages
- `nqptp_*.deb` — optional but recommended for AirPlay 2 multi‑room sync
- `shairport-sync_*.deb` — AirPlay receiver; build with RAOP2 support for AirPlay 2

## How devices install packages
- `pkg/install.sh` checks APT and local `pkg/*.deb` files and enqueues broker installs:
  - `/usr/bin/apt-get update` + `/usr/bin/apt-get -y install <pkg>` for repo packages
  - `/usr/bin/dpkg -i /opt/airplay_wyse/pkg/<file>.deb` for local artifacts in the tag
- The root broker processes the queue with a strict allow‑list; no arbitrary sudo.

## Building shairport-sync with AirPlay 2
1. Install build deps on a Debian build host:
   - `sudo apt-get install -y git build-essential autoconf automake libtool pkg-config libasound2-dev libpopt-dev libconfig-dev libssl-dev libavahi-client-dev libsoxr-dev libplist-dev avahi-daemon libmd-dev libgcrypt20-dev`
2. Build nqptp (optional but recommended):
   - `git clone https://github.com/mikebrady/nqptp && cd nqptp && autoreconf -fi && ./configure --with-systemd-startup && make && make deb`
3. Build shairport-sync with RAOP2:
   - `git clone https://github.com/mikebrady/shairport-sync && cd shairport-sync`
   - `autoreconf -fi`
   - `./configure --with-alsa --with-avahi --with-ssl=openssl --with-soxr --with-metadata --with-dbus --with-raop2`
   - `make deb`
4. Copy the resulting `.deb` files into this repo’s `pkg/` directory and create a signed tag.

Notes
- Devices only install if the version is newer than the installed one.
- If APT provides `nqptp`, the installer prefers the repo version; otherwise the local `.deb` is used if present.
