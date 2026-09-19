"""Generate the demo recordings.

    python -m app.demo.generate                 # all scenarios -> backend/demo_calls/
    python -m app.demo.generate --only 01_clean_approve 02_wrong_rate_hold
    python -m app.demo.generate --list

Writes, per scenario, a stereo WAV (agent left / customer right, with the
transcript embedded), a sidecar <key>.transcript.json, and one DEMO_SHEET.md
listing every file, its expected outcome and the values to enter.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import BACKEND_ROOT
from app.demo.scenarios import SCENARIOS, Scenario
from app.demo.synth import SynthesisError, render_scenario

DEFAULT_OUT = BACKEND_ROOT / "demo_calls"


def _sheet(scenarios: list[Scenario], durations: dict[str, float]) -> str:
    lines = [
        "# Demo calls",
        "",
        "Synthetic recordings for the CIMET QA SaleGuard demo. Every person, address, number and email is invented.",
        "",
        "**How to use one:** Add Lead -> choose the `.wav` -> **Transcribe** -> the sale details fill in from the",
        "file name (edit anything you like) -> **Save & Score**.",
        "",
        "Audio is dual-channel: agent on the left, customer on the right, so speakers are separated exactly.",
        "",
        "| File | Length | Expected gate | What it demonstrates |",
        "|---|---|---|---|",
    ]
    for s in scenarios:
        length = durations.get(s.key)
        shown = f"{int(length // 60)}:{int(length % 60):02d}" if length else "-"
        lines.append(f"| `{s.filename}` | {shown} | **{s.expected_gate}** | {s.title}. {s.demonstrates} |")

    lines += ["", "## Values per file", ""]
    for s in scenarios:
        p, a = s.preset, s.preset["attributes"]
        lines += [
            f"### {s.filename}  ->  {s.expected_gate}",
            "",
            f"- Lead ID: `{p['lead_id']}`   Retailer: Aurora Energy Retail   Plan: Aurora Saver Plus",
            f"- Agent: {p['agent_name']}   Campaign: {p['campaign']}   Call date/time: {p['call_datetime']}",
            f"- Customer: {p['customer_name']}   Email: {p['customer_email']}   Phone: {p['customer_phone']}",
            f"- DOB: {p['customer_dob']}   Address: {p['address_line1']}, {p['suburb']} {p['state']} {p['postcode']}",
            f"- NMI: {a['nmi']}   Fuel: {a['fuel_type']}   Life support: {a['life_support']}   "
            f"Concession: {a['concession']}   Move-in: {a['move_in_date']}",
            f"- Payment collected on call: {a['payment_collected']}"
            + (f"   Gift card value: {a['gift_card_value']}" if 'gift_card_value' in a else ""),
            "",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic demo call recordings.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder")
    parser.add_argument("--only", nargs="*", help="scenario keys to generate")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args()

    chosen = [s for s in SCENARIOS if not args.only or s.key in args.only]
    if args.list:
        for s in SCENARIOS:
            print(f"{s.key:34s} {s.expected_gate:13s} {s.title}")
        return 0
    if not chosen:
        print(f"No scenario matches {args.only}. Use --list.")
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    durations: dict[str, float] = {}
    for scenario in chosen:
        try:
            rendered = render_scenario(scenario)
        except SynthesisError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        wav_path = args.out / scenario.filename
        wav_path.write_bytes(rendered.wav_bytes)
        (args.out / f"{scenario.key}.transcript.json").write_text(
            json.dumps({"language": "en-AU", "source": "EMBEDDED_DEMO", "segments": rendered.segments}, indent=2),
            encoding="utf-8",
        )
        durations[scenario.key] = rendered.duration_seconds
        print(f"{scenario.filename:36s} {rendered.duration_seconds:6.1f}s  {len(rendered.wav_bytes) / 1_048_576:5.1f} MB"
              f"  {len(rendered.segments):3d} segments  -> {scenario.expected_gate}")

    (args.out / "DEMO_SHEET.md").write_text(_sheet(SCENARIOS, {**durations}), encoding="utf-8")
    print(f"\nWrote {len(chosen)} recording(s) and DEMO_SHEET.md to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
