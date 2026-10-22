# Development

SAT-xtreme lives on the branch `xtreme` of [justink0k/SAT-xtreme](https://github.com/justink0k/SAT-xtreme). It
is based on the official SAT tag `4.2.1`, with the official `develop` branch merged in.

## Principles

- Every new behaviour is **opt-in** behind its own option and off by default; with everything off, the fork
  behaves like the official SAT. Bug fixes may apply without an option.
- Hard limits: never exceed the configured maximum setpoint, never touch hot water (except the opt-in
  keep-warm switch), and keep the failover to the thermostat on the bus working.
- Every change gets tests, an entry in `CHANGES_XTREME.md` and a version bump.
- Everything in the repository is in English; translations live in `custom_components/sat/translations/`.

## Layout

| Path | What |
|---|---|
| `custom_components/sat/` | The integration. Files from the official SAT keep their names. |
| `custom_components/sat/xtreme/` | Modules that only exist in the fork: `profile.py` (options, presets), `opv.py` (self-learning OPV), `calibration.py`, `sensor.py`, `binary_sensor.py`, `switch.py`, `dashboard.py`. |
| `tests/` | Tests; the fork's tests start with `test_xtreme_`. |
| `docs/` and `mkdocs.yml` | This manual. |
| `dev/` | The development setup of the official SAT (Docker Compose with a test configuration). |
| `CHANGES_XTREME.md` | Every change compared to the official SAT, as the GPL-3.0 license requires. |
| `RELEASING.md` | How to make a release. |

## Running the tests

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

## Building this manual

```bash
.venv/bin/pip install -r requirements_docs.txt
.venv/bin/mkdocs serve
```

Then open `http://127.0.0.1:8000`. A push to `xtreme` that changes `docs/` or `mkdocs.yml` publishes the manual
to GitHub Pages through the workflow `.github/workflows/docs.yml`. The test `tests/test_xtreme_manual.py`
checks that every option of the fork and every fork entity is described in the manual.

## Releases

Versions have the form `4.2.1-xtreme.N` (a `-`, not a `+`, because Home Assistant and HACS ignore everything
after a `+`). See [RELEASING.md](https://github.com/justink0k/SAT-xtreme/blob/xtreme/RELEASING.md).

## Adding a boiler preset

See [Boiler presets](boiler_presets.md#adding-a-preset-for-your-boiler).
