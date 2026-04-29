#!/usr/bin/env python3
"""
Read catalog_per_example_audit_results.tsv, re-request rows with HTTP 400 and
urllib 'Bad Request' reason, and write a copy where the notes column holds the
full response body (JSON as one line when parseable).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def fetch_body(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.dumps({"unexpected": resp.status, "body": resp.read().decode("utf-8")[:500]})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace").strip()
        if not raw:
            return json.dumps({"http_status": e.code, "reason": e.reason, "body": ""})
        try:
            parsed = json.loads(raw)
            return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        except json.JSONDecodeError:
            return json.dumps({"http_status": e.code, "reason": e.reason, "body": raw})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input",
        default="scripts/catalog_per_example_audit_results.tsv",
    )
    ap.add_argument(
        "--output",
        default="scripts/catalog_per_example_audit_400_badrequest_enriched.tsv",
        help="Full audit TSV with 400 Bad Request notes replaced by error JSON.",
    )
    ap.add_argument(
        "--output-400-only",
        default="scripts/catalog_per_example_audit_400_badrequest_only.tsv",
        help="Same columns, only rows that were HTTP 400 Bad Request (enriched notes).",
    )
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    with open(args.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    fieldnames = list(rows[0].keys()) if rows else []

    to_fetch: list[tuple[int, str]] = []
    for i, r in enumerate(rows):
        if r.get("http_status") != "400":
            continue
        note = (r.get("notes") or "").strip()
        if note != "Bad Request":
            continue
        url = (r.get("url") or "").strip()
        if not url:
            continue
        to_fetch.append((i, url))

    bodies: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_body, url, args.timeout): idx for idx, url in to_fetch}
        for fut in as_completed(futs):
            idx = futs[fut]
            try:
                bodies[idx] = fut.result()
            except Exception as e:
                bodies[idx] = json.dumps({"error": str(e)[:500]})

    out_rows = []
    for i, r in enumerate(rows):
        r2 = dict(r)
        if i in bodies:
            r2["notes"] = bodies[i]
        out_rows.append(r2)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter="\t",
            quoting=csv.QUOTE_MINIMAL,
            extrasaction="ignore",
        )
        w.writeheader()
        w.writerows(out_rows)

    only_400 = [out_rows[i] for i in sorted(bodies.keys())]
    if args.output_400_only:
        with open(args.output_400_only, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=fieldnames,
                delimiter="\t",
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",
            )
            w.writeheader()
            w.writerows(only_400)

    print(
        f"Wrote {len(out_rows)} rows to {args.output} "
        f"({len(bodies)} notes replaced with error JSON). "
        f"Wrote {len(only_400)} rows to {args.output_400_only}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
