# Changes in the Intergas Xtreme fork

This file lists every change of this fork compared to upstream
[Smart Autotune Thermostat (SAT)](https://github.com/Alexwijn/SAT), as required by the GPL-3.0
license: what was changed, in which files, and when.

The fork is based on upstream tag `4.2.1`.

## Switches

All switches live in one place: *Settings → Devices & services → SAT → Configure → Xtreme profile*.
They are stored as regular SAT options, so they survive updates and restarts. Every switch is **off**
by default; with all switches off the fork behaves like upstream SAT `4.2.1` plus the fixes listed
under "Base".

The constants and decision logic of the profile are in `custom_components/sat/xtreme_profile.py`.
All decisions are logged at debug level with the prefix `Xtreme profile:`. To see them, add this to
`configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.sat: debug
```

## Going back to the official SAT

1. Turn off all switches under *Xtreme profile* (optional, but it makes the switch-over clean).
2. In HACS, remove the custom repository `https://github.com/justink0k/SAT-xtreme`.
3. Install the official *Smart Autotune Thermostat* from HACS and restart Home Assistant.

The configuration is compatible: the domain (`sat`) and the configuration format are unchanged. The
extra *Xtreme profile* options are ignored by the official version.

---

## Base (`4.2.1+xtreme.0`, 2026-10-21)

No switch: these are fixes that apply to everyone.

- Cherry-picked from upstream `develop` (not yet in a release):
  - `7d43560` *Make sure the coordinator is all setup during overshoot calculation*
    (`custom_components/sat/config_flow.py`).
  - `042dcca` *Fix heater state command to use the correct activation logic*
    (`custom_components/sat/mqtt/ems.py`; only affects EMS-ESP).
  - `6e05470` *Check whether heater needs to be turned off because all valves are closed*
    (`custom_components/sat/climate.py`).
- The overshoot protection calculation (calibration) never sends a control setpoint above the
  configured maximum setpoint. Before, it used `min(62, MaxTSet reported by the boiler)`, which could
  be higher than the configured maximum
  (`custom_components/sat/overshoot_protection.py`).
- Fork metadata: display name *SAT (Intergas Xtreme fork)*, version, documentation and issue tracker
  links (`custom_components/sat/manifest.json`, `hacs.json`), fork notice on top of `README.md`, this
  file, `.gitignore`.
