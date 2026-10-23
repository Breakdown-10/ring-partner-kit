"""
Command-line interface for Ring Partner Kit and Ring Twin.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from .models import RingWebhookEnvelope
from .verifier import RingWebhookVerifier
from .twin import RingTwinSimulator


def verify_command(args):
    verifier = RingWebhookVerifier(secret=args.secret)
    body_bytes = args.body.encode("utf-8")
    valid = verifier.verify(body_bytes, args.signature)
    if valid:
        print("[SUCCESS] Webhook signature is VALID.")
        sys.exit(0)
    else:
        print("[FAILED] Webhook signature is INVALID.")
        sys.exit(1)


def twin_emit_command(args):
    twin = RingTwinSimulator(webhook_secret=args.secret)
    now = datetime.now(timezone.utc)
    skip_wake = args.anomaly == "wake"
    skip_lunch = args.anomaly == "lunch"
    extra_night = args.anomaly == "night"

    events = twin.generate_day_routine(
        day_date=now,
        skip_wake=skip_wake,
        skip_lunch=skip_lunch,
        extra_night_wandering=extra_night,
    )
    print(f"[*] Emitting {len(events)} synthesized events to {args.url} (anomaly={args.anomaly})...")

    success = 0
    for evt in events:
        try:
            resp = twin.emit_webhook(args.url, evt)
            if resp.status_code in (200, 201, 202):
                success += 1
            else:
                print(f"[-] HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[-] Error delivering event: {e}")

    print(f"[+] Delivered {success}/{len(events)} events successfully.")


def twin_backfill_command(args):
    twin = RingTwinSimulator()
    events = twin.backfill_history(days=args.days)
    data = [e.model_dump() for e in events]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[+] Exported {len(events)} events spanning {args.days} days to {args.output}")


def main():
    parser = argparse.ArgumentParser(prog="ring-partner-kit", description="Ring Partner Developer Toolkit")
    subparsers = parser.add_subparsers(dest="subcommand", help="Sub-commands")

    v_parser = subparsers.add_parser("verify", help="Verify HMAC signature of a webhook payload")
    v_parser.add_argument("--secret", required=True, help="Webhook signing secret")
    v_parser.add_argument("--signature", required=True, help="Ring signature header value")
    v_parser.add_argument("--body", required=True, help="Raw body string")

    args = parser.parse_args()
    if args.subcommand == "verify":
        verify_command(args)
    else:
        parser.print_help()


def twin_main():
    parser = argparse.ArgumentParser(prog="ring-twin", description="Ring Twin Hardware Simulator")
    subparsers = parser.add_subparsers(dest="subcommand", help="Sub-commands")

    emit_p = subparsers.add_parser("emit", help="Emit synthesized events to a webhook endpoint")
    emit_p.add_argument("--url", required=True, help="Webhook receiver URL")
    emit_p.add_argument("--secret", default="test_secret_32bytes_hex_string_demo", help="Webhook signing secret")
    emit_p.add_argument("--anomaly", choices=["none", "wake", "lunch", "night"], default="none", help="Inject anomaly type")

    bf_p = subparsers.add_parser("backfill", help="Export historical synthetic events to JSON")
    bf_p.add_argument("--days", type=int, default=21, help="Number of historical days to generate")
    bf_p.add_argument("--output", default="synthetic_history.json", help="Output file path")

    args = parser.parse_args()
    if args.subcommand == "emit":
        twin_emit_command(args)
    elif args.subcommand == "backfill":
        twin_backfill_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
