"""Extract invoice images and print one line per file; used for the single live run and the replay check.

  python scripts/extract_images.py                 # replay: read data/model_cache only, no key, no model calls
  python scripts/extract_images.py --live --yes    # LIVE: calls Gemini for cache misses, saves to data/model_cache/
                                                   # (needs GEMINI_API_KEY and GEMINI_MODEL in .env)
Options: --dir DIR (default data/inputs/images), --refresh (live only: ignore the cache and call again).
Prints file, status, source, cache key and the raw JSON; never prints the API key.
"""

import argparse
import sys

from invoice_recon import config
from invoice_recon.extraction.gemini import GeminiProvider
from invoice_recon.extraction.service import MIME_TYPES, extract_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="call Gemini for cache misses")
    parser.add_argument("--yes", action="store_true", help="confirm that real model calls are intended")
    parser.add_argument("--refresh", action="store_true", help="live only: ignore existing cache entries")
    parser.add_argument("--dir", default=str(config.INPUTS_DIR / "images"))
    args = parser.parse_args()

    provider = None
    mode = "replay"
    if args.live:
        if not args.yes:
            print("Refusing a live run without --yes (it makes real Gemini calls).", file=sys.stderr)
            return 2
        if not config.GEMINI_API_KEY or not config.GEMINI_MODEL:
            print("GEMINI_API_KEY and GEMINI_MODEL must be set in .env for a live run.", file=sys.stderr)
            return 2
        mode = "live"
        provider = GeminiProvider(config.GEMINI_API_KEY)

    from pathlib import Path

    paths = sorted(p for p in Path(args.dir).iterdir() if p.suffix.lower() in MIME_TYPES)
    failures = 0
    for path in paths:
        result = extract_document(
            path.stem, path, mode=mode, provider=provider, use_simulations=False,
            simulated_failures=frozenset(), refresh=args.refresh and args.live,
        )
        failures += result.status != "ok"
        print(f"{path.stem}: status={result.status} source={result.source} model={result.model} "
              f"key={(result.cache_key or '')[:12]} error={result.error}")
        if result.raw is not None:
            print("  " + result.raw.model_dump_json())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
