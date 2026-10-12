# swo-dem

Reusable Python examples for the SolarWinds Observability (SWO) SaaS **REST API**,
focused on Digital Experience Monitoring (DEM): websites, URI checks (TCP, ping, DNS, UDP),
synthetic transactions and page speed.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SWO_TOKEN='<your API Access token>'   # Settings > API Tokens in SWO
```

Optional settings:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SWO_REGION` | `na-01` | Data center; base URL becomes `https://api.<region>.cloud.solarwinds.com/v1` |
| `SWO_BASE_URL` | — | Full base URL; overrides `SWO_REGION` |

The token is read only from the environment and is never printed.

## Examples

### `examples/01_list_availability_checks.py`

Lists availability checks with their current **native status** (`up`, `down`, `paused`,
`maintenance`, `unknown`). This is the `state.nativeState` attribute on each entity, not the
`healthState` shown in the UI.

```bash
python examples/01_list_availability_checks.py                   # website checks only (default)
python examples/01_list_availability_checks.py --types uri       # all URI checks (tcp, ping, dns, udp)
python examples/01_list_availability_checks.py --types website,uri
python examples/01_list_availability_checks.py --types ping,dns  # only ping and DNS URI checks
python examples/01_list_availability_checks.py --types all       # every check kind
python examples/01_list_availability_checks.py --types tcp --json
python examples/01_list_availability_checks.py --types uri --details  # add response time, last test, TCP port
python examples/01_list_availability_checks.py --limit 10         # stop after 10 checks (the first ones the API returns)
python examples/01_list_availability_checks.py --csv > checks.csv
python examples/01_list_availability_checks.py --fail-on-down    # exit 2 if anything is down
```

Endpoints used:

- `GET /v1/entities?type=Website` and `GET /v1/entities?type=Uri` (paginated). The entity
  `attributes` give the native status (`state.nativeState`), the URI protocol (`protocols`)
  and the target (`url` or `host`). A default run needs only these calls.
- `GET /v1/dem/websites/{id}` and `GET /v1/dem/uris/{id}`, only with `--details`, or when an
  entity has no native status or a TCP port in its attributes. These add response time, last
  test time and the TCP port.

Problems are listed first (`down`, then `error`, `unknown`, and so on). A failed detail call
keeps the row, records the error in `message`, and does not stop the run.

## Layout

```
swo_dem/        reusable client: auth, base URL, retry with backoff, pagination
examples/       runnable scripts, one per use case
```

Tests are kept outside this repository.
