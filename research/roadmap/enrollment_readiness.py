"""Outcome-free next-study readiness and assumption-based sample-size checks."""

import argparse
import ctypes
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def kernel_clock():
    if not sys.platform.startswith("linux"):
        return {
            "available": False,
            "reason": "not_linux",
            "independent_utc_accuracy_verified": False,
        }
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        query = libc.adjtimex
        query.argtypes = [ctypes.c_void_p]
        query.restype = ctypes.c_int
        # All-zero modes means query only. Oversized buffer avoids ABI field-layout guesses.
        state = query(ctypes.create_string_buffer(4096))
        if state < 0:
            return {
                "available": False,
                "reason": "kernel_query_unavailable",
                "independent_utc_accuracy_verified": False,
            }
        return {
            "available": True,
            "provider": "Linux adjtimex modes=0 query only",
            "kernel_time_state": state,
            "kernel_reports_time_ok": state == 0,
            "clock_modified": False,
            "independent_utc_accuracy_verified": False,
            "scope": "Kernel-reported state is not source/root-dispersion evidence, a container clock certificate or independent UTC verification. It does not retroactively satisfy the prior chrony requirement.",
        }
    except (OSError, AttributeError):
        return {
            "available": False,
            "reason": "kernel_query_not_supported",
            "independent_utc_accuracy_verified": False,
        }


def required_days(effect, daily_sd, design_effect=1):
    effect, sd, de = Decimal(str(effect)), Decimal(str(daily_sd)), Decimal(str(design_effect))
    if not all(v.is_finite() and v > 0 for v in (effect, sd, de)):
        raise ValueError("Positive finite effect, daily SD and design effect required")
    return max(
        2, math.ceil((1.959963984540054 + 0.8416212335729143) ** 2 * float((sd / effect) ** 2 * de))
    )


def build(output):
    design_path = ROOT / "research/roadmap/matched_design_v1.json"
    design = json.loads(design_path.read_text())
    freeze = json.loads((ROOT / "reports/pre_enrollment_20261116/design-freeze.json").read_text())
    if hashlib.sha256(design_path.read_bytes()).hexdigest() != freeze["design_sha256"]:
        raise ValueError("Frozen next-study design changed")
    soak = json.loads((ROOT / "reports/cloud_soak_20261116/report.json").read_text())
    preservation = ROOT / "reports/cloud_soak_20261116/preservation.json"
    remote = (
        json.loads(preservation.read_text()).get("status") == "REMOTE_READBACK_VERIFIED"
        if preservation.exists()
        else False
    )
    checks = {
        "design_hash_verified": True,
        "bounded_capture_health": all(
            v for k, v in soak["checks"].items() if k != "daemon_clock_diagnostics"
        ),
        "original_daemon_clock_requirement_met": soak["checks"]["daemon_clock_diagnostics"],
        "independent_utc_accuracy_verified": False,
        "remote_readback_verified": remote,
        "raw_normalization_and_instrument_binding_qualified": False,
        "independent_discovery_contrast_activity_measured": False,
        "executable_inference_sources_frozen_for_enrollment": False,
        "exact_future_dates_published": design["calendar"]["fixed_dates"] is not None,
    }
    planned = design["calendar"]["untouched_test_days"]
    scenarios = [
        {
            "effect_usdt_per_opportunity": str(effect),
            "sd_of_paired_daily_mean_same_units": str(sd),
            "assumed_design_effect": de,
            "approximate_required_days": required_days(effect, sd, de),
            "exceeds_planned_test_days": required_days(effect, sd, de) > planned,
        }
        for effect in (Decimal(".001"), Decimal(".005"), Decimal(".01"))
        for sd in (Decimal(".005"), Decimal(".02"), Decimal(".05"))
        for de in (1, 2)
    ]
    report = {
        "status": "BLOCKED_NOT_ENROLLED",
        "checks": checks,
        "kernel_clock_query": kernel_clock(),
        "planned_untouched_test_days": planned,
        "power_scenarios": scenarios,
        "power_method": "Two-sided 5% alpha, 80% power normal approximation for paired daily means: ceil((z.975+z.8)^2*(SD/effect)^2*assumed_design_effect), at least two dates.",
        "power_limitations": "Every effect, SD and dependence inflation is hypothetical, not estimated from the released unpaired primary study or three demo trades. Known-variance normal approximations ignore finite-sample uncertainty and are not power guarantees. No sample size or threshold is changed by this diagnostic.",
        "activity_check": "Next study requires at least 30 nonzero paired opportunities on at least 10 test dates. One contrast/day for 28 days would fail the count gate. New design-specific discovery eligibility/action counts are required; 21,388 old leader-triggered labels are not estimates of matched-policy activity.",
        "calendar_action": "Do not activate or choose retrospective dates while any qualification gate is missing. Any design change must be a new public version before future enrollment, preserving v1 and the completed study.",
        "capital_deployment": False,
        "new_orders": 0,
        "active_study_outcomes_read": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "readiness.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    r = build(a.out)
    print(
        json.dumps(
            {"status": r["status"], "checks": r["checks"], "kernel_clock": r["kernel_clock_query"]}
        )
    )
