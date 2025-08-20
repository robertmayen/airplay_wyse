Checklist

- [ ] Touched both `inventory/hosts/wyse-sony.yml` and `inventory/hosts/wyse-dac.yml` when host-affecting fields changed (`nic`, `alsa.vendor_id`, `alsa.product_id`, `alsa.serial`, `airplay_name`).
- [ ] Canary plan noted (which host, how long) before promotion to all devices.

Notes
- If only one host needs a temporary difference, document why and when it will be reconciled.
- Ensure release tags are signed; devices verify tags before applying.

