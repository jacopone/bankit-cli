# bankit-cli

Command-line tool and Python library for the statistics of Banca d'Italia, designed to be
driven by people and by coding agents alike. Data sources are interchangeable adapters behind
one interface and one output schema:

| Source | Adapter | Coverage | Access |
|---|---|---|---|
| Banca d'Italia, Base Dati Statistica (BDS) | `bdi` | BDS publications (national and territorial series) | A2A export service, documented in the BDS user guide, section 5.2 |
| European Central Bank, Data Portal | `ecb` | euro-area harmonised series, cross-country comparisons | SDMX 2.1 REST API |

> **Unofficial.** This project is not affiliated with, endorsed by, or maintained by
> Banca d'Italia or the European Central Bank. The data belong to Banca d'Italia and the ECB
> and remain subject to their terms of use (see [Data terms](#data-terms)).
>
> *Non ufficiale, non affiliato a Banca d'Italia. I dati sono di Banca d'Italia e della BCE e
> restano soggetti alle loro condizioni d'uso.*

## Install

Requires Python 3.10 or newer and no other dependency. Pick one:

```sh
pipx install git+https://github.com/jacopone/bankit-cli     # isolated, puts `bankit` on the PATH
uv tool install git+https://github.com/jacopone/bankit-cli  # same with uv
pip install git+https://github.com/jacopone/bankit-cli      # into the current environment
pip install "bankit-cli[pandas] @ git+https://github.com/jacopone/bankit-cli"   # with pandas support
```

Check it: `bankit --version`. Behind a corporate proxy, set `HTTPS_PROXY` as for any Python tool.

## First steps

```sh
bankit sources                                           # the two sources: bdi, ecb
bankit search "loans non-financial corporations" --publication BAM    # find a series key
bankit get BAM_MIR.M.1300010.MIR5411.9.950.1000.SBI77.EUR.110.997 --start 2024-01 > loans.csv
```

The first command that needs Banca d'Italia data downloads it from the BDS A2A service and caches it
for 24 hours; later calls are instant. The output is a CSV, or JSON with `--format json`, with the same
columns for every source (see below). `bankit --help` and `bankit <command> --help` list all options.

## Usage

```sh
# find series by words in their titles (BdI legends, cached locally)
bankit search "loans non-financial corporations new business" --publication BAM

# metadata: title, frequency, publication, table, first and last observation
bankit describe BAM_MIR.M.1300010.MIR5411.9.950.1000.SBI77.EUR.110.997

# observations, long format, CSV on stdout (or --format json / jsonl)
bankit get BAM_MIR.M.1300010.MIR5411.9.950.1000.SBI77.EUR.110.997 --start 2024-01

# the same concept from the ECB (source inferred from the FLOW/KEY form, or forced with ecb:)
bankit get ecb:MIR/M.IT.B.A2A.A.R.A.2240.EUR.N --start 2024-01
```

Keys: BdI series keys start with the publication code (`BAM_`, `MFN_`, `BOP_`, ...);
ECB keys are `FLOW/KEY` (`MIR/M.IT...`) or the `FLOW.KEY` form used in ECB files.
A `bdi:` or `ecb:` prefix selects the source explicitly.

Output columns, identical for every source:
`source, series_key, period, date, value, title, unit, retrieved_at, source_url`.
`period` is normalised (`2026-08`, `2026-Q2`, `2026`, `2026-09-30`) so series from different
sources join on it; it is empty when the frequency is unknown, `date` is always set.

Errors are one JSON object on stderr with a stable exit code:

| Exit | Meaning |
|---|---|
| 0 | success |
| 2 | invalid arguments |
| 3 | operation not supported by the source |
| 4 | series or publication not found |
| 5 | source or network error, including requests rejected by the source's firewall |
| 6 | `--offline` and the data is not in the cache |

Downloads are cached under `$XDG_CACHE_HOME/bankit` for 24 hours (`--refresh`, `--offline`,
`--cache-dir`).

## Python

```python
import bankit

rows = bankit.get("BAM_MIR.M.1300010.MIR5411.9.950.1000.SBI77.EUR.110.997", start="2024-01")
info = bankit.describe("ecb:MIR/M.IT.B.A2A.A.R.A.2240.EUR.N")
df = bankit.to_pandas(rows)          # requires the pandas extra
```

## Adding a source

Implement `bankit.sources.base.Source` (`search`, `describe`, `get`) returning the common
`Observation` and `SeriesInfo` types, and register it in `bankit/sources/__init__.py`.
Source-specific parsing stays inside the adapter.

## Data terms

`bankit` downloads data from the sources on request and does not redistribute it. Every row carries its
`source_url` and `retrieved_at`. Whoever publishes data obtained with `bankit` must follow the terms of the source:

- **Banca d'Italia**: statistics may be used free of charge, including commercially, on condition that the source is
  cited (for example "Fonte: Banca d'Italia") and the content is not modified. The right does not extend to
  third-party data and may be revoked in exceptional circumstances.
  <https://www.bancaditalia.it/statistiche/condizioni-utilizzo/index.html>. The datasets that Banca d'Italia lists as
  open data on <https://dati.gov.it> are released under CC BY 4.0
  (<https://www.bancaditalia.it/footer/copyright/index.html>).
- **ECB**: free reuse on condition that the source is quoted (for example "Source: ECB statistics") and that the
  statistics, including metadata, are not modified; modifications by the user must be stated explicitly.
  <https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html>
- The A2A export service of the BDS is described in the BDS user guide; availability and format are decided by
  Banca d'Italia and can change.

This repository holds no Banca d'Italia statistics. Its tests use synthetic files in the format of the BDS export
and one unmodified ECB extract with its source cited; see `tests/fixtures/SOURCES.txt`.

## Development

```sh
uv run --extra test pytest                  # offline: synthetic and recorded fixtures, network blocked
uv run --extra test pytest -m live          # opt-in: compares the live BdI and ECB sources
uv run python scripts/make_fixtures.py      # regenerate the synthetic BdI fixtures
uv run python scripts/record_fixtures.py    # re-record the ECB fixture from the live source
```

The offline tests run on every push and pull request in GitHub Actions (`.github/workflows/ci.yml`).

## License

MIT, see `LICENSE`. The licence covers the code of this repository, not the data of Banca d'Italia or the ECB.
