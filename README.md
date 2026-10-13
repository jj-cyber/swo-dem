# swo-dem

Examples for the Digital Experience Monitoring (DEM) features of the SolarWinds Observability
(SWO) SaaS **REST API**. Each example covers one DEM feature and may exist in more than one
programming language.

## DEM features and examples

The API exposes four DEM entity types (`GET /v1/entities?type=<type>`), which belong to three
features:

| DEM feature | Entity types | Example |
|-------------|--------------|---------|
| [Availability monitoring](https://documentation.solarwinds.com/en/success_center/observability/content/intro/websites/synthetic.htm) (websites and URIs: HTTP/HTTPS, ping, TCP, DNS, UDP) | `Website`, `Uri` | [01 availability checks](examples/01-availability-checks/): Python |
| Synthetic transaction checks | `SyntheticTransaction` | not yet |
| PageSpeed | `PageSpeed` | not yet |

## Setup (Python examples)

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

## Layout

```
swo_dem/                                   shared Python client: auth, base URL, retry with backoff, pagination
requirements.txt                           runtime dependencies of the Python examples
examples/
  01-availability-checks/                  one folder per example, numbered
    README.md                              what it shows, usage and sample output (all languages)
    python/                                one folder per language
      list_availability_checks.py
```

To add an example, create `examples/NN-<feature>-<topic>/` with a README and one folder per
language. A new language port of an existing example goes next to `python/` and should follow
the behaviour and output documented in that README. Only the Python examples use `swo_dem/`.

Tests are kept outside this repository.
