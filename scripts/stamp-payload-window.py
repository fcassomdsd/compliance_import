#!/usr/bin/env python3
"""Stamp a tracked demo payload's dates onto the site-visit window the seed computed.

Why this exists
---------------

`atrocore-docker/sql/seed-demo-dataset.sql` seeds the demo site visit with a window
relative to the day the seed runs (`CURRENT_DATE + 21` to `+ 22`); a ZIP committed to a
repository cannot, because its dates are frozen the day it is written. The two drift
apart within a day of each other, and the drift is not cosmetic: the canonical import
copies `checklist.startDate`/`endDate` onto the Alfresco inspection folder, which is the
*only* place an inspection's window lives (AtroCore's `inspection` table has no date
columns of its own). A stale payload therefore dates the demo's inspection into the wrong
week, and its checklist items fall out of a year-filtered provider-history report.

`atrocore-docker/scripts/demo-quickstart.sh` therefore reads the window back from the
seeded `site_visit` row, stamps a copy of each payload with it, and imports *that*. The
tracked ZIP stays a **template**: its dates are a self-consistent example, and every date
in it is re-derived here.

The derivation
--------------

The window is the anchor, and every other date keeps its distance from it:

    checklist.startDate := the window's first day
    checklist.endDate   := the window's last day
    every other date    := shifted by the same delta as the window's last day, so a
                           finding issued on the inspection's last day still lands on
                           its last day
    followUpReport.followUpDate
                        := the window's last day + N days (``--follow-up-lag-days``,
                           default 13)

A follow-up payload carries no `checklist.json` of its own — it belongs to an inspection
that lives in a different ZIP — so its lag behind the window is a declared argument rather
than something inferable from the file.

Usage
-----

    stamp-payload-window.py <source.zip> <dest.zip> --start YYYY-MM-DD --end YYYY-MM-DD

The source ZIP is never modified; evidence files are copied through byte for byte and only
the entries whose dates change are re-encoded. One line is printed per stamped field, so
the caller's log shows what moved.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import zipfile

DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")

CHECKLIST_ENTRY = "checklist.json"
FINDINGS_ENTRY = "findings.json"
FOLLOWUP_ENTRY = "followup-reports.json"

WINDOW_FIELDS = ("checklist.startDate", "checklist.endDate")

DEFAULT_FOLLOW_UP_LAG_DAYS = 13


def parse_date_only(value, label):
    if not isinstance(value, str) or not DATE_ONLY.match(value):
        raise SystemExit(f"{label}: expected a YYYY-MM-DD date, got {value!r}")
    return dt.date.fromisoformat(value)


def as_date(value):
    """A `YYYY-MM-DD` (or `YYYY-MM-DDThh:mm:ss…`) string as a date, or None."""
    if isinstance(value, str) and DATE_PREFIX.match(value):
        return dt.date.fromisoformat(value[:10])
    return None


def shift_dates(node, delta, changes, entry, path="", skip=()):
    """Shift every date string in the structure in place by `delta` days."""
    if isinstance(node, dict):
        for key in list(node):
            child = f"{path}.{key}" if path else key
            node[key] = shift_dates(node[key], delta, changes, entry, child, skip)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            node[index] = shift_dates(item, delta, changes, entry, f"{path}[{index}]", skip)
    elif isinstance(node, str) and DATE_PREFIX.match(node):
        if path in skip:
            return node
        original = node[:10]
        shifted = (dt.date.fromisoformat(original) + delta).isoformat()
        changes.append((f"{entry}: {path}", original, shifted))
        return node.replace(original, shifted, 1)
    return node


def stamp_checklist(payload, window_start, window_end):
    """Re-anchor a checklist payload on the window; returns (delta, changes)."""
    checklist = payload.get("checklist")
    if not isinstance(checklist, dict):
        raise SystemExit(f"{CHECKLIST_ENTRY}: no `checklist` object to re-anchor")

    delta = window_end - (as_date(checklist.get("endDate")) or window_end)

    # Shift the dates the checklist already carries *before* overwriting the window
    # itself, or the freshly assigned window would be shifted off its own anchor.
    changes = []
    if delta:
        shift_dates(payload, delta, changes, CHECKLIST_ENTRY, skip=WINDOW_FIELDS)

    for path, value in zip(WINDOW_FIELDS, (window_start, window_end)):
        field = path.split(".")[-1]
        old = checklist.get(field)
        checklist[field] = value.isoformat()
        changes.append((f"{CHECKLIST_ENTRY}: {path}", old, value.isoformat()))
    return delta, changes


def stamp_follow_up(payload, window_end, lag_days):
    """Date the follow-up `lag_days` after the window ends; returns changes."""
    target = (window_end + dt.timedelta(days=lag_days)).isoformat()
    entries = payload if isinstance(payload, list) else [payload]
    changes = []
    for index, entry in enumerate(entries):
        report = entry.get("followUpReport") if isinstance(entry, dict) else None
        if not isinstance(report, dict):
            continue
        old = report.get("followUpDate")
        report["followUpDate"] = target
        changes.append((f"{FOLLOWUP_ENTRY}: [{index}].followUpReport.followUpDate", old, target))
    return changes


def stamp(source, destination, window_start, window_end, follow_up_lag_days):
    """Rewrite `source` into `destination`; returns the list of (path, old, new)."""
    with zipfile.ZipFile(source) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]

    decoded = {}
    for info, data in entries:
        if not info.filename.endswith(".json"):
            continue
        try:
            decoded[info.filename] = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

    changes = []
    touched = set()

    checklist = decoded.get(CHECKLIST_ENTRY)
    if checklist is not None:
        delta, checklist_changes = stamp_checklist(checklist, window_start, window_end)
        changes.extend(checklist_changes)
        touched.add(CHECKLIST_ENTRY)
    else:
        delta = dt.timedelta(0)

    findings = decoded.get(FINDINGS_ENTRY)
    if findings is not None:
        shift_dates(findings, delta, changes, FINDINGS_ENTRY)
        touched.add(FINDINGS_ENTRY)

    follow_ups = decoded.get(FOLLOWUP_ENTRY)
    if follow_ups is not None:
        changes.extend(stamp_follow_up(follow_ups, window_end, follow_up_lag_days))
        touched.add(FOLLOWUP_ENTRY)

    if not touched:
        raise SystemExit(
            f"{source}: carries none of {CHECKLIST_ENTRY}, {FINDINGS_ENTRY} or "
            f"{FOLLOWUP_ENTRY}, so there is no window to derive — is this a payload?"
        )

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as out:
        for info, data in entries:
            if info.filename in touched:
                data = json.dumps(decoded[info.filename], ensure_ascii=False, indent=2).encode("utf-8")
            out.writestr(info, data)

    return changes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source", help="the tracked payload ZIP (never modified)")
    parser.add_argument("destination", help="where to write the stamped copy")
    parser.add_argument("--start", required=True, help="the window's first day, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="the window's last day, YYYY-MM-DD")
    parser.add_argument(
        "--follow-up-lag-days",
        type=int,
        default=DEFAULT_FOLLOW_UP_LAG_DAYS,
        help="days after the window ends at which a follow-up payload is dated (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    window_start = parse_date_only(args.start, "--start")
    window_end = parse_date_only(args.end, "--end")
    if window_end < window_start:
        raise SystemExit(f"--end ({window_end}) is before --start ({window_start})")

    changes = stamp(args.source, args.destination, window_start, window_end, args.follow_up_lag_days)
    print(f"{args.source} -> {args.destination}: window {window_start} to {window_end}")
    for path, old, new in changes:
        print(f"  {path}: {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
