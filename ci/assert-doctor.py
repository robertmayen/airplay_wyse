#!/usr/bin/env python3
"""Gate CI on an airplay-doctor JSON report (read from stdin).

Runners have no sound hardware, so checks that need a real DAC are exempt;
everything else (services, features, nqptp interface, ports, mDNS of THIS
box, identity) must not fail.
"""

import json
import sys

HARDWARE_ONLY = {"alsa:card"}

report = json.load(sys.stdin)
for c in report["checks"]:
    print(f"  [{c['status']:>7}] {c['name']}: {c['detail']}")
bad = [c["name"] for c in report["checks"] if c["status"] == "fail" and c["name"] not in HARDWARE_ONLY]
if bad:
    print(f"::error::airplay-doctor failed: {', '.join(bad)}")
    sys.exit(1)
