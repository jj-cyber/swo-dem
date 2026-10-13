# Example 01: availability checks

Reports the current state of your SolarWinds Observability
[availability monitoring](https://documentation.solarwinds.com/en/success_center/observability/content/intro/websites/synthetic.htm)
checks in one list: which websites and URIs are up, down, paused, in maintenance or unknown,
with problems first. Availability checks are the `Website` entities (HTTP/HTTPS) and the `Uri`
entities (ping, TCP port, DNS or UDP).

The status is the same one the SWO DEM Availability UI shows: the entity attribute
`state.nativeState` (`up`, `down`, `paused`, `maintenance`, `unknown`). It is not the entity
`healthState` (GOOD, BAD, ...), which is a separate health signal. Following the SWO definition,
an entity is `down` after two consecutive failed checks.

| Language | Script |
|----------|--------|
| Python 3 | [`python/list_availability_checks.py`](python/list_availability_checks.py) |

Run it from the `python/` folder after the setup in the [main README](../../README.md):

```bash
python list_availability_checks.py                   # website checks only (default)
python list_availability_checks.py --types uri       # all URI checks (tcp, ping, dns, udp)
python list_availability_checks.py --types website,uri
python list_availability_checks.py --types ping,dns  # only ping and DNS URI checks
python list_availability_checks.py --types all       # website and uri checks
python list_availability_checks.py --types tcp --json
python list_availability_checks.py --types uri --details  # add response time, last test, TCP port
python list_availability_checks.py --limit 10         # stop after 10 checks (the first ones the API returns)
python list_availability_checks.py --csv > checks.csv
python list_availability_checks.py --fail-on-down    # exit 2 if anything is down
```

Endpoints used:

- `GET /v1/entities?type=Website` and `GET /v1/entities?type=Uri` (paginated). The entity
  `attributes` give the status (`state.nativeState`), the URI protocol (`protocols`) and the
  target (`url` or `host`). A default run needs only these calls.
- `GET /v1/dem/websites/{id}` and `GET /v1/dem/uris/{id}`, only with `--details`, or when an
  entity has no status in its attributes. These add the response time, the last test time and
  the TCP port.

Problems are listed first (`down`, then `error`, `unknown`, and so on). `error` is not an SWO
state: the script uses it when a detail call fails and no status was known. A failed detail call
keeps the row, records the error in `message`, and does not stop the run.

## Example output

A report from `--types all --details`. The check names and hosts are made up. A TCP check shows
its port next to the kind. `LAST TEST` and `RESPONSE MS` show `-` when there is no value: a
DNS check, or a check that failed, has no response time. Without `--details` these two columns
are `-` for every row.

```text
NAME           KIND      TARGET                    STATUS  LAST TEST             RESPONSE MS
Database       tcp:5432  db.example.com            down    2026-01-15T09:42:15Z  -
Shop checkout  website   https://shop.example.com  down    2026-01-15T09:41:12Z  5003
Legacy portal  website   https://old.example.com   paused  2026-01-14T22:10:00Z  310
Company site   website   https://www.example.com   up      2026-01-15T09:42:30Z  142
Docs           website   https://docs.example.com  up      2026-01-15T09:42:05Z  87
Gateway        ping      gw.example.com            up      2026-01-15T09:42:20Z  2.3
Mail relay     tcp:25    mail.example.com          up      2026-01-15T09:42:01Z  12.4
Public DNS     dns       ns1.example.com           up      2026-01-15T09:41:50Z  -
```

With `--json`, each check is one object (`--csv` has the same fields as columns):

```json
{
  "name": "Database",
  "kind": "tcp",
  "target": "db.example.com",
  "port": 5432,
  "status": "down",
  "last_test_time": "2026-01-15T09:42:15Z",
  "last_response_ms": null,
  "last_error_time": "2026-01-15T09:42:15Z",
  "entity_id": "e-1000000000000000006",
  "message": null
}
```

With `--fail-on-down` the exit code is 2 when any check is down, so the script can gate a cron
job or CI step.
