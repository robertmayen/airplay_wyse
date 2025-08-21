# Networking & mDNS

- Devices reside on the same LAN/VLAN; multicast must not be filtered.
- IGMP snooping: ensure Querier present or disable snooping to avoid mDNS loss.
- `.local` is reserved for mDNS; FQDNs use `audio.home.arpa` for SSH/DNS.
- Required discovery: `_airplay._tcp` and `_raop._tcp` via Avahi.
 - AirPlay 2 timing (NQPTP): allow PTP on UDP ports 319 and 320 on the LAN; filtering these will break multi-room sync.
