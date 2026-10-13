"""List DEM checks (Website, Uri, SyntheticTransaction, PageSpeed) with their native status.

Uses the SolarWinds Observability REST API:

- ``GET /v1/entities?type=<DEM entity type>`` (paginated). The entity attributes carry the
  status (``state.nativeState``: up, down, paused, maintenance, unknown), the target
  (``url`` or ``host``) and, for a URI, its protocol (PING, DNS, TCP, UDP).
- ``--details`` also calls ``GET /v1/dem/websites/{id}`` or ``GET /v1/dem/uris/{id}`` per
  Website and Uri for response time, last test time and TCP port. The same call is the
  fallback when an entity has no native status.

Environment: ``SWO_TOKEN`` (required), ``SWO_REGION`` or ``SWO_BASE_URL`` (optional).

Examples::

    python examples/01_list_availability_checks.py
    python examples/01_list_availability_checks.py --types website,uri --csv
    python examples/01_list_availability_checks.py --types tcp --details --json
    python examples/01_list_availability_checks.py --fail-on-down
    python examples/01_list_availability_checks.py --types all --limit 10
"""

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Make the repository root importable when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swo_dem import MissingTokenError, SwoApiError, SwoClient  # noqa: E402

# DEM entity types.
WEBSITE = "Website"
URI = "Uri"
SYNTHETIC_TRANSACTION = "SyntheticTransaction"
PAGESPEED = "PageSpeed"
ENTITY_TYPES = (WEBSITE, URI, SYNTHETIC_TRANSACTION, PAGESPEED)
# Uri checks are told apart by their protocol; each is selectable on its own.
URI_KINDS = ("tcp", "ping", "dns", "udp")
DEFAULT_TYPES = (WEBSITE,)
# Only these have a DEM configuration endpoint for ``--details``.
CONFIG_PATHS = {WEBSITE: "dem/websites", URI: "dem/uris"}
NATIVE_STATUS_ATTRIBUTE = "state.nativeState"
PAGE_SIZE = 100

# Lower value sorts first: problems at the top of the report.
STATUS_ORDER = {"down": 0, "error": 1, "unknown": 2, "maintenance": 3, "paused": 4, "up": 5}
FIELDS = [
    "name",
    "kind",
    "target",
    "port",
    "status",
    "last_test_time",
    "last_response_ms",
    "last_error_time",
    "entity_id",
    "message",
]


def parse_types(value):
    """Turn ``--types`` into a de-duplicated tuple of entity types and/or Uri protocols."""
    choices = {entity_type.lower(): (entity_type,) for entity_type in ENTITY_TYPES}
    choices.update({kind: (kind,) for kind in URI_KINDS})
    choices["all"] = ENTITY_TYPES
    selectors = []
    for item in value.lower().split(","):
        item = item.strip()
        if item and item not in choices:
            raise argparse.ArgumentTypeError(
                f"unknown type {item!r}; choose from {', '.join(choices)}"
            )
        selectors += [m for m in choices.get(item, ()) if m not in selectors]
    return tuple(selectors)


def positive_int(value):
    """argparse type for options that must be an integer of at least 1."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def row_from_entity(entity):
    """Build a report row from the entity list alone (no extra API call)."""
    attributes = entity.get("attributes") or {}
    if entity["type"] == URI:
        protocols = attributes.get("protocols") or ["unknown"]
        kind = protocols[0].lower()
    else:
        kind = entity["type"].lower()
    target = attributes.get("url") if kind == "website" else attributes.get("host")
    return {
        "name": entity.get("displayName") or entity.get("name", ""),
        "kind": kind,
        "target": target or attributes.get("hostname") or "",
        "port": attributes.get("port") if kind == "tcp" else None,
        "status": attributes.get(NATIVE_STATUS_ATTRIBUTE) or None,
        "last_test_time": None,
        "last_response_ms": None,
        "last_error_time": None,
        "entity_id": entity["id"],
        "message": None,
    }


def fetch_details(client, entity_type, row):
    """Fill a row from its DEM configuration. A failure is recorded in ``message``."""
    try:
        config = client.get(f"{CONFIG_PATHS[entity_type]}/{row['entity_id']}")
        if not isinstance(config, dict):
            raise ValueError("unexpected response body (not a JSON object)")
    except (SwoApiError, OSError, ValueError) as error:
        row["message"] = str(error)
        row["status"] = row["status"] or "error"
        return
    row["status"] = row["status"] or config.get("status")
    row["target"] = row["target"] or config.get("url") or config.get("ipOrDomain") or ""
    if row["kind"] == "tcp" and row["port"] is None:
        row["port"] = ((config.get("availabilityCheckSettings") or {}).get("tcp") or {}).get("port")
    row["last_test_time"] = config.get("lastTestTime")
    row["last_response_ms"] = config.get("lastResponseTime")
    row["last_error_time"] = config.get("lastErrorTime")


def collect_checks(client, selectors, details=False, workers=32, limit=None):
    """Return report rows for every entity matching ``selectors`` (see ``parse_types``).

    The ``Uri`` entity type takes every Uri check; protocol kinds (e.g. ``tcp``) alone
    keep just the Uri checks of those protocols.

    With ``limit`` the listing stops once that many rows are collected, so later pages
    and their detail calls are never requested. The rows are the first ones the API
    returns, not the first after sorting.

    Detail calls (Website and Uri only) run when ``details`` is set or a row lacks its
    status. A failing call keeps the row and never aborts the run.
    """
    wanted = [
        entity_type for entity_type in ENTITY_TYPES
        if entity_type in selectors or (entity_type == URI and set(URI_KINDS) & set(selectors))
    ]
    max_rows = limit or float("inf")
    rows, pending = [], []
    for entity_type in wanted:
        params = {"type": entity_type, "pageSize": PAGE_SIZE}
        for entity in client.paginate("entities", "entities", params):
            if len(rows) >= max_rows:
                break
            row = row_from_entity(entity)
            if entity_type == URI and URI not in selectors and row["kind"] not in selectors:
                continue
            rows.append(row)
            if entity_type in CONFIG_PATHS and (details or row["status"] is None):
                pending.append((entity_type, row))
            if len(rows) >= max_rows:
                break

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda pair: fetch_details(client, *pair), pending))

    for row in rows:
        row["status"] = row["status"] or "unknown"
    return rows


def sort_rows(rows):
    """Problems first (down, error, ...), then by name."""
    return sorted(rows, key=lambda row: (STATUS_ORDER.get(row["status"], 2), row["name"].lower()))


def render_table(rows):
    """Plain-text, column-aligned table."""
    table = [["NAME", "KIND", "TARGET", "STATUS", "LAST TEST", "RESPONSE MS"]]
    for row in rows:
        kind = f"{row['kind']}:{row['port']}" if row["port"] else row["kind"]
        response = "-" if row["last_response_ms"] is None else row["last_response_ms"]
        table.append([row["name"], kind, row["target"], row["status"],
                      row["last_test_time"] or "-", response])
    widths = [max(len(str(cell)) for cell in column) for column in zip(*table)]
    return "\n".join(
        "  ".join(str(cell).ljust(width) for cell, width in zip(line, widths)) for line in table
    )


def render_csv(rows, stream):
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--types",
        type=parse_types,
        default=DEFAULT_TYPES,
        help="comma-separated: website, uri (all Uri checks), synthetictransaction, pagespeed, "
             "or a single Uri protocol: tcp, ping, dns, udp; 'all' for every entity type "
             "(default: website)",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="also fetch each Website/Uri DEM configuration: response time, last test, TCP port "
             "(one extra API call per check)",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help="stop after this many checks (the first ones the API returns); default: all",
    )
    parser.add_argument(
        "--workers", type=positive_int, default=32, help="parallel API calls (default: 32)"
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="print JSON instead of a table")
    output.add_argument("--csv", action="store_true", help="print CSV instead of a table")
    parser.add_argument(
        "--fail-on-down",
        action="store_true",
        help="exit with code 2 if any check is down (useful in cron or CI)",
    )
    return parser


def main(argv=None, client=None, stdout=None):
    args = build_parser().parse_args(argv)
    stdout = stdout or sys.stdout
    try:
        client = client or SwoClient()
        rows = sort_rows(
            collect_checks(
                client, args.types, details=args.details, workers=args.workers, limit=args.limit
            )
        )
    except MissingTokenError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except SwoApiError as error:
        print(f"error: API request failed: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        # requests.RequestException is an OSError; ValueError covers a non-JSON body.
        print(f"error: could not reach the API or read its response: {error}", file=sys.stderr)
        return 1

    if args.json:
        json.dump(rows, stdout, indent=2)
        stdout.write("\n")
    elif args.csv:
        render_csv(rows, stdout)
    else:
        stdout.write(render_table(rows) + "\n" if rows else "No checks found.\n")

    if args.fail_on_down and any(row["status"] == "down" for row in rows):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
