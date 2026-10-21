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

## Step 1: prime the setpoint during the PWM off phase (`4.2.1+xtreme.1`, 2026-10-21)

Switch: **Prime the setpoint during the PWM off phase** (`xtreme_prime_setpoint`).

**Why.** In gateway mode the OTGW only replaces the control setpoint inside the MsgID 1 messages that
the thermostat on the bus sends; it does not send MsgID 1 by itself. A Nest sends MsgID 1 only about
once every 150 seconds, while the central heating enable bit (MsgID 0) goes out every few seconds.
Upstream SAT lowers the setpoint to 10 °C in every PWM off phase and raises it at the start of every
on phase, so the boiler gets the heating demand right away but the setpoint 0 to 150 seconds later.

**What changes when the switch is on.**

- PWM off phase: the control setpoint stays at the minimum setpoint (the overshoot protection value)
  instead of 10 °C, and the heating demand is turned off explicitly (`CH=0`). The boiler then already
  has the right setpoint when the next on phase turns the demand on.
- PWM on phase, continuous operation, HVAC mode off, hot water, areas and calibration are unchanged.
  The maximum setpoint is still applied to every setpoint that is sent.
- The heating demand is no longer derived only from the height of the setpoint: during a PWM off
  phase it is off, otherwise it follows the upstream rule (on above 28.2 °C).
- Heater commands are decided on the last command sent instead of on the central heating status bit
  reported by the boiler, which lags behind and does not follow the demand while the boiler is
  anti-cycling. A command is not sent again within 30 seconds, and after that only when the boiler
  does not confirm it. Without this, a PWM on phase that ends while the boiler is still anti-cycling
  could leave the demand on together with the primed setpoint.
- A primed setpoint without heating demand and without flame is reported as boiler status `idle`,
  as with the 10 °C setpoint upstream. This prevents a false `stuck_off` flame status during the off
  phase and keeps the boiler temperature tracker paused, as upstream.
- Side effect: during the off phase the relative modulation state is `off` (upstream: `cold`), so the
  maximum relative modulation command keeps the value of the on phase instead of switching back.
  Boilers that ignore the modulation limit (such as the Intergas Xtreme) are not affected.
- Failover: unchanged. SAT keeps refreshing `CS=` while heating; when SAT or Home Assistant stops,
  the gateway drops the control setpoint override after about a minute and the thermostat on the bus
  takes over both the setpoint and the heating demand.

**Files.** `custom_components/sat/xtreme_profile.py` (new), `custom_components/sat/const.py`,
`custom_components/sat/climate.py`, `custom_components/sat/coordinator.py`,
`custom_components/sat/config_flow.py`, `custom_components/sat/translations/en.json`,
`custom_components/sat/manifest.json`, `tests/test_xtreme_prime_setpoint.py` (new).
