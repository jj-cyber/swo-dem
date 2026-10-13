# swo-dem

Examples for the Digital Experience Monitoring (DEM) features of the SolarWinds Observability
(SWO) SaaS **REST API**. Each example covers one DEM feature and may exist in more than one
programming language.

> **Unofficial project.** This is not an official SolarWinds repository and is not affiliated
> with, endorsed or supported by SolarWinds. The examples are based only on the public SWO REST
> API and the public SolarWinds Observability documentation. SolarWinds and SolarWinds
> Observability are trademarks of SolarWinds Worldwide, LLC. Use the examples at your own risk
> and check the [official documentation](https://documentation.solarwinds.com/en/success_center/observability/content/observability_getting_started_guide.htm)
> for the current API behaviour.

## DEM features and examples

The API exposes four DEM entity types (`GET /v1/entities?type=<type>`), which belong to three
features:

| DEM feature | Entity types | Example |
|-------------|--------------|---------|
| [Availability monitoring](https://documentation.solarwinds.com/en/success_center/observability/content/intro/websites/synthetic.htm) (websites and URIs: HTTP/HTTPS, ping, TCP, DNS, UDP) | `Website`, `Uri` | [01 availability checks](examples/01-availability-checks/): Python |
| Synthetic transaction checks | `SyntheticTransaction` | not yet |
| PageSpeed | `PageSpeed` | not yet |

## Setup (Python examples)

First create an API token (organization owners and admins only):

1. In SWO, go to **Settings > API Tokens** and click **Create API token**.
2. Enter a name, select the type **API Access** and create the token.
3. Copy the token. You pass it to the examples as `SWO_TOKEN`.

Details are in the [API tokens documentation](https://documentation.solarwinds.com/en/success_center/observability/content/settings/api-tokens.htm).
An API Access token can also create, modify and delete data (for example a website check), so
keep it secret.

Then set up the environment:

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
