"""Command line entrypoint for AirPlay Wyse management."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import alsa, config, deploy, identity, packages, pipewire, shairport, state, systemd_utils, utils

REPO_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aw",
        description="Manage AirPlay Wyse setup and diagnostics",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    setup = subparsers.add_parser("setup", help="Install and configure AirPlay Wyse")
    _add_common_config_args(setup)
    setup.add_argument("--force-identity", action="store_true", help="Reset AirPlay identity")
    setup.add_argument(
        "--statistics",
        action="store_true",
        help="Enable Shairport statistics output",
    )
    setup.add_argument(
        "--no-statistics",
        action="store_true",
        help="Disable Shairport statistics even if previously enabled",
    )
    setup.add_argument(
        "--force-rate",
        type=int,
        choices=[44100, 48000, 88200, 96000],
        help="Pin PipeWire clock to a specific rate",
    )

    apply_p = subparsers.add_parser("apply", help="Re-render configuration with updated options")
    _add_common_config_args(apply_p)
    apply_p.add_argument("--force-identity", action="store_true", help="Reset AirPlay identity")
    apply_p.add_argument(
        "--statistics",
        action="store_true",
        help="Enable Shairport statistics output",
    )
    apply_p.add_argument(
        "--no-statistics",
        action="store_true",
        help="Disable Shairport statistics",
    )

    ident = subparsers.add_parser("identity", help="Identity management commands")
    ident_sub = ident.add_subparsers(dest="identity_command", metavar="identity-command")
    ident_ensure = ident_sub.add_parser("ensure", help="Ensure AirPlay identity is sane")
    ident_ensure.add_argument("--force", action="store_true", help="Force identity reset")

    policy_alsa = subparsers.add_parser("policy-alsa", help="Ensure ALSA policy is applied")
    policy_alsa.add_argument("--device", help="Explicit ALSA hw device (e.g. hw:1,0)")
    policy_alsa.add_argument("--json", action="store_true", help="Print JSON summary")

    policy_pw = subparsers.add_parser("policy-pipewire", help="Ensure PipeWire policy is applied")
    policy_pw.add_argument(
        "--force-rate",
        type=int,
        choices=[44100, 48000, 88200, 96000],
        help="Pin PipeWire clock to a specific rate",
    )
    policy_pw.add_argument("--json", action="store_true", help="Print JSON summary")

    systemd_cmd = subparsers.add_parser("systemd", help="Systemd integration")
    systemd_sub = systemd_cmd.add_subparsers(dest="systemd_command", metavar="systemd-command")
    systemd_sub.add_parser("install", help="Install/refresh systemd units")

    health = subparsers.add_parser("health", help="Emit a condensed health snapshot")
    health.add_argument("--json", action="store_true", help="Return JSON payload")

    return parser


def _add_common_config_args(cmd: argparse.ArgumentParser) -> None:
    cmd.add_argument("--name", help="Shairport advertised name")
    cmd.add_argument("--device", help="Preferred ALSA hardware device (hw:X,Y)")
    cmd.add_argument("--mixer", help="Optional ALSA mixer control")
    cmd.add_argument("--interface", help="Preferred network interface for mDNS")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "setup":
            handle_setup(args)
        elif args.command == "apply":
            handle_apply(args)
        elif args.command == "identity" and args.identity_command == "ensure":
            handle_identity(force=args.force)
        elif args.command == "policy-alsa":
            handle_policy_alsa(args)
        elif args.command == "policy-pipewire":
            handle_policy_pipewire(args)
        elif args.command == "systemd" and args.systemd_command == "install":
            handle_systemd_install()
        elif args.command == "health":
            handle_health(args)
        else:
            parser.error("unknown command combination")
    except PermissionError as exc:
        parser.error(str(exc))
    except utils.CommandError as exc:
        parser.error(str(exc))
    return 0


def handle_setup(args: argparse.Namespace) -> None:
    utils.ensure_root()
    deploy.install_runtime(REPO_ROOT)

    packages.ensure_packages(["jq", "alsa-utils", "avahi-daemon"])
    stack = shairport.ensure_stack()
    if not stack.has_airplay2:
        raise utils.CommandError("shairport-sync does not report AirPlay 2 support")

    alsa_policy = alsa.ensure_policy(manual_device=args.device)
    pipewire_policy = pipewire.ensure_policy(force_rate=args.force_rate)

    config_updates: dict[str, object] = {}
    if args.name:
        config_updates["name"] = args.name
    if args.mixer:
        config_updates["mixer"] = args.mixer
    if args.interface:
        config_updates["interface"] = args.interface

    config_updates.update(
        {
            "device": "default",
            "output_rate": alsa_policy.anchor_hz if alsa_policy.requires_soxr else None,
            "interpolation": "soxr" if alsa_policy.requires_soxr and stack.has_soxr else None,
        }
    )

    if alsa_policy.requires_soxr and not stack.has_soxr:
        raise utils.CommandError(
            "shairport-sync lacks libsoxr while hardware needs 48 kHz anchor"
        )

    if args.statistics and args.no_statistics:
        raise utils.CommandError("--statistics and --no-statistics are mutually exclusive")
    if args.statistics:
        config_updates["statistics"] = True
    elif args.no_statistics:
        config_updates["statistics"] = False

    state.update_state({"config": config_updates})

    identity.ensure_identity(force=args.force_identity)
    _render_and_write_config()

    deploy.install_systemd_units(REPO_ROOT)
    systemd_utils.daemon_reload()
    systemd_utils.enable("avahi-daemon.service", now=True, ignore_failure=True)
    systemd_utils.enable("nqptp.service", now=True, ignore_failure=True)
    systemd_utils.enable("airplay-wyse-alsa-policy.service", now=False, ignore_failure=True)
    systemd_utils.enable("airplay-wyse-pw-policy.service", now=False, ignore_failure=True)
    systemd_utils.enable("airplay-wyse-identity.service", now=False, ignore_failure=True)
    systemd_utils.enable("shairport-sync.service", now=True, ignore_failure=False)

    print("Setup complete")
    print(f"  ALSA device: {alsa_policy.device} (anchor {alsa_policy.anchor_hz} Hz)")
    if pipewire_policy.present:
        rate = pipewire_policy.force_rate or "auto"
        print(f"  PipeWire allowed rates: {', '.join(str(r) for r in pipewire.ALLOWED_RATES)} (force={rate})")


def handle_apply(args: argparse.Namespace) -> None:
    utils.ensure_root()
    stack = shairport.ensure_stack()
    if not stack.has_airplay2:
        raise utils.CommandError("shairport-sync does not report AirPlay 2 support")
    alsa_policy = alsa.ensure_policy(manual_device=args.device)

    config_updates: dict[str, object] = {
        "device": "default",
        "output_rate": alsa_policy.anchor_hz if alsa_policy.requires_soxr else None,
        "interpolation": "soxr" if alsa_policy.requires_soxr and stack.has_soxr else None,
    }
    if args.name:
        config_updates["name"] = args.name
    if args.mixer:
        config_updates["mixer"] = args.mixer
    if args.interface:
        config_updates["interface"] = args.interface
    if args.statistics and args.no_statistics:
        raise utils.CommandError("--statistics and --no-statistics are mutually exclusive")
    if args.statistics:
        config_updates["statistics"] = True
    elif args.no_statistics:
        config_updates["statistics"] = False

    if alsa_policy.requires_soxr and not stack.has_soxr:
        raise utils.CommandError(
            "shairport-sync lacks libsoxr while hardware needs 48 kHz anchor"
        )

    state.update_state({"config": config_updates})

    identity.ensure_identity(force=args.force_identity)
    _render_and_write_config()
    systemd_utils.restart("shairport-sync.service")
    print("Configuration applied")


def handle_identity(*, force: bool) -> None:
    utils.ensure_root()
    result = identity.ensure_identity(force=force)
    _render_and_write_config()
    payload = {
        "mac": result.mac,
        "interface": result.interface,
        "changed": result.changed,
        "synthetic": result.synthetic,
    }
    print(json.dumps(payload, indent=2))


def handle_policy_alsa(args: argparse.Namespace) -> None:
    utils.ensure_root()
    policy = alsa.ensure_policy(manual_device=args.device)
    payload = {
        "device": policy.device,
        "anchor_hz": policy.anchor_hz,
        "requires_soxr": policy.requires_soxr,
        "card": policy.card,
        "card_id": policy.card_id,
        "dev_num": policy.dev_num,
        "is_usb": policy.is_usb,
        "changed": policy.changed,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"ALSA device: {policy.device} (anchor {policy.anchor_hz} Hz, usb={policy.is_usb})")
        if policy.requires_soxr:
            print("  Note: requires libsoxr resampling")


def handle_policy_pipewire(args: argparse.Namespace) -> None:
    utils.ensure_root()
    policy = pipewire.ensure_policy(force_rate=args.force_rate)
    payload = {
        "present": policy.present,
        "changed": policy.changed,
        "force_rate": policy.force_rate,
        "allowed_rates": pipewire.ALLOWED_RATES,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if not policy.present:
            print("PipeWire not detected; policy skipped")
        else:
            print(
                f"PipeWire policy ensured (force={policy.force_rate or 'auto'}, changed={policy.changed})"
            )


def handle_systemd_install() -> None:
    utils.ensure_root()
    deploy.install_systemd_units(REPO_ROOT)
    systemd_utils.daemon_reload()
    print("Systemd units refreshed")


def handle_health(args: argparse.Namespace) -> None:
    summary = {}
    summary["nqptp"] = _service_status("nqptp.service")
    summary["shairport"] = _service_status("shairport-sync.service")
    summary["identity"] = _service_status("airplay-wyse-identity.service")
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("Health summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")


def _service_status(service: str) -> str:
    result = utils.run_cmd(["systemctl", "is-active", service], check=False)
    return result.stdout.strip() or "inactive"


def _render_and_write_config() -> None:
    data = state.load_state()
    cfg_data = data.get("config", {})
    cfg_obj = config.ShairportConfig(
        name=cfg_data.get("name") or "Wyse DAC",
        device=cfg_data.get("device") or "default",
        mixer=cfg_data.get("mixer"),
        interface=cfg_data.get("interface"),
        hardware_address=cfg_data.get("hardware_address"),
        output_rate=cfg_data.get("output_rate"),
        statistics=bool(cfg_data.get("statistics", False)),
        interpolation=cfg_data.get("interpolation"),
        airplay_device_id=cfg_data.get("airplay_device_id"),
    )
    rendered = config.render_config(cfg_obj)
    config.write_config(rendered)


if __name__ == "__main__":
    sys.exit(main())
