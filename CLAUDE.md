# Notes for Claude

SAT-xtreme is an unofficial fork of Smart Autotune Thermostat (SAT), a Home Assistant integration that
controls a central heating boiler. Changes are made carefully, one step at a time.

## How to work in this repository

- Propose first, build later: show a proposal (files, changes, risks) and wait for an explicit
  approval before changing files, committing, tagging or pushing.
- Every new behaviour is opt-in behind its own option and off by default; with everything off the
  fork behaves like upstream SAT. Bug fixes may apply without an option.
- Every change gets tests, an entry in `CHANGES_XTREME.md`, and a version bump in
  `custom_components/sat_xtreme/manifest.json` (format `X.Y.Z-xtreme.N`, see `RELEASING.md`).
- Everything in the repository (code, comments, log messages, README, changelog, commit messages) is in
  English. Translations live in `custom_components/sat_xtreme/translations/`.
- Never put personal data (entity IDs, addresses, logs of a specific home) in the repository; the
  `local/` folder is ignored by git for that.
- Hard limits: never exceed the configured maximum setpoint, never touch hot water (the only exception is the
  opt-in keep-warm switch, which only changes the keep-warm function when the user turns it off), and keep the
  failover to the thermostat on the bus working.

## Releases

Whenever the version in `manifest.json` is raised, propose to make a GitHub release as described in
`RELEASING.md`, and first show the exact commands and the full text of the release notes. Only run them
after approval.
