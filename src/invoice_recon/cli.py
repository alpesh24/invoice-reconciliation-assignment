"""Command line: run / reconcile / reset."""

import argparse
import sys

from invoice_recon import config, pipeline, storage
from invoice_recon.documents import DuplicateFileIdError


def _fmt_cents(value: int | None) -> str:
    return "-" if value is None else f"{value // 100}.{value % 100:02d}"


def _print_result(states, summary) -> None:
    print(f"{'file_id':<22}{'seq':>4}  {'status':<18}{'source':<10}{'diff USD':>10}")
    for state in sorted(states.values(), key=lambda s: s.ingest_seq):
        rec = state.reconciliation
        print(
            f"{state.file_id:<22}{state.ingest_seq:>4}  {rec.status if rec else '-':<18}"
            f"{state.extraction.source or '-':<10}{_fmt_cents(rec.difference_cents if rec else None):>10}"
        )
    drafted = [s.note for s in states.values() if s.note]
    print(
        f"notes: {len(drafted)} drafted, {sum(1 for n in drafted if n['guard_passed'])} passed the number guard; "
        f"sources: {', '.join(sorted({n['source'] for n in drafted})) or '-'}"
    )
    print("counts:", ", ".join(f"{k}={v}" for k, v in summary.counts.items()))
    print(
        f"recoverable USD {_fmt_cents(summary.recoverable_cents)}; "
        f"net difference USD {_fmt_cents(summary.net_difference_cents)} (discrepant invoices only)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invoice_recon.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="process all documents (MODEL_MODE from .env)")
    sub.add_parser("reconcile", help="recompute from saved extractions, no model calls")
    reset = sub.add_parser("reset", help="delete data/state/ (keeps the model cache)")
    reset.add_argument("--yes", action="store_true", help="confirm deletion")
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            print(f"MODEL_MODE={config.MODEL_MODE}")
            _print_result(*pipeline.run_pipeline())
        elif args.command == "reconcile":
            states, summary = pipeline.reconcile_all()
            if not states:
                print("No saved state; run `cli run` first.")
                return 1
            _print_result(states, summary)
        else:
            if not args.yes:
                print("reset deletes data/state/; pass --yes to confirm", file=sys.stderr)
                return 2
            print("state deleted" if storage.reset_state() else "nothing to delete")
    except (storage.StorageError, DuplicateFileIdError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
