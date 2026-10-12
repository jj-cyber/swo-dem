"""List DEM availability checks (Website, URI protocols) with their native status.

Uses the SolarWinds Observability REST API:

- ``GET /v1/entities?type=Website`` and ``GET /v1/entities?type=Uri`` (paginated).
  Each entity carries everything the default report needs in ``attributes``:

  - ``state.nativeState``: availability (up, down, paused, maintenance, unknown)
  - ``protocols``: check protocol of a URI (PING, DNS, TCP, UDP)
  - ``url`` (websites) or ``host`` (URIs): the target

- ``--details`` additionally calls ``GET /v1/dem/websites/{id}`` or
  ``GET /v1/dem/uris/{id}`` for each check to add response time, last test time
  and the TCP port. Those calls also run as a fallback when an entity has no
  native status in its attributes.

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

WEBSITE = "Website"
URI = "Uri"
URI_KINDS = ("tcp", "ping", "dns", "udp")
ALL_KINDS = ("website",) + URI_KINDS
KIND_GROUPS = {"uri": URI_KINDS, "all": ALL_KINDS}
DEFAULT_KINDS = ("website",)
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


def parse_kinds(value):
    """Turn ``--types`` into a validated, de-duplicated tuple of check kinds.

    Groups expand to their members: ``uri`` means every URI check (tcp, ping,
    dns, udp) and ``all`` means every kind.
    """
    kinds = []
    for item in value.split(","):
        item = item.strip().lower()
        if not item:
            continue
        if item not in ALL_KINDS and item not in KIND_GROUPS:
            raise argparse.ArgumentTypeError(
                f"unknown check type {item!r}; choose from {', '.join(ALL_KINDS + ('uri',))} or 'all'"
            )
        for kind in KIND_GROUPS.get(item, (item,)):
            if kind not in kinds:
                kinds.append(kind)
    return tuple(kinds)


def positive_int(value):
    """argparse type for options that must be an integer of at least 1."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def list_entities(client, entity_type):
    """Yield every entity of ``entity_type`` (follows pagination)."""
    yield from client.paginate(
        "entities", "entities", {"type": entity_type, "pageSize": PAGE_SIZE}
    )


def entity_kind(entity):
    """``website``, or the URI protocol in lower case (ping, dns, tcp, udp)."""
    if entity["type"] == WEBSITE:
        return "website"
    protocols = (entity.get("attributes") or {}).get("protocols") or []
    return protocols[0].lower() if protocols else "unknown"


def row_from_entity(entity):
    """Build a report row from the entity list alone (no extra API call)."""
    attributes = entity.get("attributes") or {}
    kind = entity_kind(entity)
    if kind == "website":
        target = attributes.get("url", "")
    else:
        target = attributes.get("host") or attributes.get("hostname") or ""
    return {
        "name": entity.get("displayName") or entity.get("name", ""),
        "kind": kind,
        "target": target,
        "port": attributes.get("port") if kind == "tcp" else None,
        "status": attributes.get(NATIVE_STATUS_ATTRIBUTE) or None,
        "last_test_time": None,
        "last_response_ms": None,
        "last_error_time": None,
        "entity_id": entity["id"],
        "message": None,
    }


def apply_config(row, config):
    """Fill a row from its DEM configuration (``--details`` or fallback)."""
    settings = config.get("availabilityCheckSettings") or {}
    if row["status"] is None:
        row["status"] = config.get("status") or None
    if not row["target"]:
        row["target"] = config.get("url") or config.get("ipOrDomain") or ""
    if row["kind"] == "tcp" and row["port"] is None:
        row["port"] = (settings.get("tcp") or {}).get("port")
    row["last_test_time"] = config.get("lastTestTime")
    row["last_response_ms"] = config.get("lastResponseTime")
    row["last_error_time"] = config.get("lastErrorTime")


def needs_config(row, details):
    """True when a row needs its DEM configuration to be complete."""
    if details or row["status"] is None:
        return True
    return row["kind"] == "tcp" and row["port"] is None


def collect_checks(client, kinds, details=False, workers=32, limit=None):
    """Return report rows for every entity whose check kind is in ``kinds``.

    With ``limit`` the listing stops once that many rows are collected, so
    later pages and their detail calls are never requested. The rows are the
    first ones the API returns, not the first after sorting.

    Only the entity lists are fetched unless ``details`` is set or a row lacks
    its status or TCP port. A failing detail call keeps the row and records the
    error in ``message``; it never aborts the run.
    """
    entity_types = []
    if "website" in kinds:
        entity_types.append(WEBSITE)
    if any(kind in kinds for kind in URI_KINDS):
        entity_types.append(URI)

    pending = []
    rows = []
    for entity_type in entity_types:
        if limit is not None and len(rows) >= limit:
            break
        for entity in list_entities(client, entity_type):
            row = row_from_entity(entity)
            if row["kind"] not in kinds:
                continue
            rows.append(row)
            if needs_config(row, details):
                pending.append((entity, row))
            if limit is not None and len(rows) >= limit:
                break

    def enrich(pair):
        entity, row = pair
        try:
            config = client.get(f"{CONFIG_PATHS[entity['type']]}/{entity['id']}")
            if not isinstance(config, dict):
                raise ValueError("unexpected response body (not a JSON object)")
            apply_config(row, config)
        except (SwoApiError, OSError, ValueError) as error:
            row["message"] = str(error)
            if row["status"] is None:
                row["status"] = "error"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(enrich, pending))

    for row in rows:
        row["status"] = row["status"] or "unknown"
    return rows


def sort_rows(rows):
    """Problems first (down, error, ...), then by name."""
    return sorted(rows, key=lambda row: (STATUS_ORDER.get(row["status"], 2), row["name"].lower()))


def render_table(rows):
    """Plain-text, column-aligned table."""
    headers = ["NAME", "KIND", "TARGET", "STATUS", "LAST TEST", "RESPONSE MS"]
    lines = [
        [row["name"], _kind_label(row), row["target"], row["status"],
         row["last_test_time"] or "-", _text(row["last_response_ms"])]
        for row in rows
    ]
    table = [headers] + lines
    widths = [max(len(str(cell)) for cell in column) for column in zip(*table)]
    fmt = "  ".join(f"{{:<{width}}}" for width in widths)
    return "\n".join(fmt.format(*(str(cell) for cell in line)) for line in table)


def _kind_label(row):
    return f"{row['kind']}:{row['port']}" if row["port"] else row["kind"]


def _text(value):
    return "-" if value is None else str(value)


def render_csv(rows, stream):
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--types",
        type=parse_kinds,
        default=DEFAULT_KINDS,
        help="comma-separated: website, uri (all URI checks), or any of tcp,ping,dns,udp; "
             "'all' for everything (default: website)",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="also fetch each check's DEM configuration: response time, last test, TCP port "
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
