#!/usr/bin/env python3
"""check_upstream — compare upstream mikebrady releases against the role's
version pins and (optionally) rewrite them. Stdlib only.

The pure core (parse_pins / plan_bumps / rewrite_pins) is unit-tested; all
network I/O lives in main(). shairport-sync is never auto-bumped across
`shairport_major` — the configure-flag profile and required-feature set differ
per major, so that jump is a human decision, surfaced as a notice instead.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

REPOS = {"shairport-sync": "shairport_sync", "nqptp": "nqptp"}
API = "https://api.github.com/repos/mikebrady"


def _vtuple(tag: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", tag))


def parse_pins(text: str) -> dict:
    return dict(re.findall(r'^([a-z_]+): "([^"]*)"', text, re.M))


def plan_bumps(current: dict, latest: dict) -> dict:
    plan = {"_notices": []}
    sps = latest.get("shairport-sync", "").lstrip("v")
    if sps:
        if str(_vtuple(sps)[0]) != current["shairport_major"]:
            if _vtuple(sps) > _vtuple(current["shairport_sync_version"]):
                plan["_notices"].append(
                    f"shairport-sync {sps} available but crosses major "
                    f"{current['shairport_major']}->{_vtuple(sps)[0]}; not auto-bumped")
        elif _vtuple(sps) > _vtuple(current["shairport_sync_version"]):
            plan["shairport_sync_version"] = {"from": current["shairport_sync_version"], "to": sps}
    nq = latest.get("nqptp", "").lstrip("v")
    if nq and _vtuple(nq) > _vtuple(current["nqptp_version"]):
        plan["nqptp_version"] = {"from": current["nqptp_version"], "to": nq}
    return plan


def rewrite_pins(text: str, new_values: dict) -> str:
    for key, value in new_values.items():
        text = re.sub(rf'^{key}: "[^"]*"', f'{key}: "{value}"', text, flags=re.M)
    return text


# --- network layer (not unit-tested) ----------------------------------------

def _api_get(path: str) -> dict | None:
    req = urllib.request.Request(f"{API}/{path}")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        if err.code == 404:  # repo has no Releases -> no data, skip
            return None
        raise


def latest_release_tag(repo: str) -> str:
    data = _api_get(f"{repo}/releases/latest")
    return data["tag_name"] if data else ""


def tag_commit_sha(repo: str, tag: str) -> str:
    """Resolve a tag to its commit (mikebrady mixes lightweight/annotated tags)."""
    ref = _api_get(f"{repo}/git/ref/tags/{tag}")
    if not ref:
        return ""
    obj = ref["object"]
    if obj["type"] == "tag":  # annotated: follow to the tagged commit
        obj = _api_get(f"{repo}/git/tags/{obj['sha']}")["object"]
    return obj["sha"]


def summarize(plan: dict, shas: dict) -> str:
    lines = ["## Upstream version bumps", "", "| pin | from | to | commit |", "|---|---|---|---|"]
    for key, bump in sorted(plan.items()):
        if key == "_notices":
            continue
        commit_key = key.replace("_version", "_commit")
        lines.append(f"| `{key}` | {bump['from']} | {bump['to']} | `{shas.get(commit_key, '?')[:12]}` |")
    for repo in REPOS:
        lines.append(f"- release notes: https://github.com/mikebrady/{repo}/releases")
    for notice in plan["_notices"]:
        lines.append(f"- **notice:** {notice}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="check_upstream")
    parser.add_argument("--check", action="store_true", help="print the bump plan as JSON")
    parser.add_argument("--apply", metavar="DEFAULTS", help="rewrite pins in this file")
    parser.add_argument("--summary-out", metavar="MD", help="write a markdown summary (PR body)")
    args = parser.parse_args(argv)

    with open(args.apply or "roles/airplay/defaults/main.yml", encoding="utf-8") as fh:
        text = fh.read()
    current = parse_pins(text)

    latest = {repo: latest_release_tag(repo) for repo in REPOS}
    plan = plan_bumps(current, latest)

    new_values = {}
    for key, bump in plan.items():
        if key == "_notices":
            continue
        repo = next(r for r, prefix in REPOS.items() if key.startswith(prefix))
        new_values[key] = bump["to"]
        sha = tag_commit_sha(repo, latest[repo])
        if sha:
            new_values[key.replace("_version", "_commit")] = sha

    if args.check:
        print(json.dumps({"plan": plan, "new_values": new_values}, indent=2))
    if args.summary_out:
        with open(args.summary_out, "w", encoding="utf-8") as fh:
            fh.write(summarize(plan, new_values))
    if args.apply and new_values:
        with open(args.apply, "w", encoding="utf-8") as fh:
            fh.write(rewrite_pins(text, new_values))
        print(f"updated {args.apply}: {', '.join(sorted(new_values))}")
    elif args.apply:
        print("no bumps needed")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
