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

## Step 2: do not manage the modulation limit (`4.2.1+xtreme.2`, 2026-10-21)

Switches: **Do not manage the modulation limit** (`xtreme_ignore_modulation_limit`), with the
settings **Rated maximum heating power** (`xtreme_boiler_maximum_power`, default 19.5 kW) and
**Rated minimum heating power** (`xtreme_boiler_minimum_power`, default 3.9 kW).

**Why.** The Intergas Xtreme ignores the maximum relative modulation (MsgID 14 is answered with
Data-Invalid, and with `MM=0` it still modulates up to 100 %), but it does report its relative
modulation level (MsgID 17) correctly. Upstream already reads the reported modulation for the OTGW
over MQTT; the flag `supports_relative_modulation` that is `False` for Intergas is not used anywhere.
What does not work is managing the limit: SAT keeps sending `MM=0` / `MM=100`.

**What changes when the switch is on.**

- `supports_relative_modulation_management` is `False`: SAT no longer sends the modulation limit in
  the control loop. Once after startup it sends the neutral value `MM=100`, so no old limit stays
  active on the gateway.
- `supports_relative_modulation` is `True`, also for Intergas, Ideal, Geminox and Nefit.
- The power sensor (and the consumption sensor, when configured) are still created. Upstream only
  creates them when the modulation limit is managed.
- When the boiler does not report its capacity (MsgID 15), the power sensor uses the rated heating
  power from the options. A capacity reported by the boiler always wins.
- The binary sensor that compares the requested and the reported modulation limit is no longer
  created; it has no meaning without a managed limit. Its entity remains in the entity registry as
  unavailable and can be removed there.

**Files.** `custom_components/sat/xtreme_profile.py`, `custom_components/sat/const.py`,
`custom_components/sat/coordinator.py`, `custom_components/sat/climate.py`,
`custom_components/sat/sensor.py`, `custom_components/sat/config_flow.py`,
`custom_components/sat/fake/__init__.py`, `custom_components/sat/translations/en.json`,
`custom_components/sat/manifest.json`, `tests/xtreme_helpers.py` (new),
`tests/test_xtreme_modulation.py` (new).

## Step 3: align PWM with the boiler timing (`4.2.1+xtreme.3`, 2026-10-21)

Switch: **Align PWM with the boiler timing** (`xtreme_boiler_timing`), with the settings
**Anti-cycling time of the boiler** (`xtreme_anti_cycling_time`, default 300 s, Intergas parameter
P036), **Anti-cycling margin** (`xtreme_anti_cycling_margin`, default 15 s), **Minimum burn time**
(`xtreme_minimum_burn_time`, default 360 s) and **Minimum duty cycle** (`xtreme_minimum_duty_cycle`,
default 7.5 %).

**Why.** Upstream counts the on time of a PWM block from the moment the heating demand goes on. When
the boiler is still anti-cycling (after its own previous burn, or after a short hot water flame of
the comfort function), or waits for the setpoint, that waiting time is lost and the real burn is much
shorter than planned. Upstream can also plan off phases of 180 seconds, shorter than the anti-cycling
time of the boiler, and burns of 3 minutes, which barely pay off the start.

**What changes when the switch is on.**

- The on time counts burn time: seconds with the flame on for heating. Seconds with hot water do not
  count. If no flame appears within the anti-cycling wait plus 15 seconds (330 s by default), the
  on time counts anyway (a warning is logged). An on phase never lasts longer than twice the planned
  on time plus that timeout.
- A new on phase starts only when the anti-cycling time plus margin (315 s by default) has passed
  since the last flame, for heating or for hot water, and no hot water is active. The setpoint is
  already primed in the meantime when step 1 is on.
- The minimum burn time replaces the upstream minimum on time of 180 seconds. All duty cycle ranges
  of upstream scale with it; with 3 cycles per hour, a duty cycle of 20 % now gives 6 minutes on and
  24 minutes off (upstream: 4 minutes on and 16 minutes off).
- Below the minimum duty cycle SAT does not burn at all, as upstream. Upstream derives this threshold
  from the minimum on time (half of its share); the profile keeps it at a fixed value (7.5 %) so a
  longer minimum burn time results in longer off phases instead of no heating.
- New sensors: **PWM Burn Time** (burn time of the last completed on phase, with the planned on time
  and the current burn time as attributes) and **Anti-cycling Remaining**.

**Files.** `custom_components/sat/xtreme_profile.py`, `custom_components/sat/xtreme_sensor.py` (new),
`custom_components/sat/const.py`, `custom_components/sat/pwm.py`, `custom_components/sat/flame.py`,
`custom_components/sat/coordinator.py`, `custom_components/sat/climate.py`,
`custom_components/sat/util.py`, `custom_components/sat/sensor.py`,
`custom_components/sat/config_flow.py`, `custom_components/sat/translations/en.json`,
`custom_components/sat/manifest.json`, `tests/test_xtreme_boiler_timing.py` (new).

## Step 4: self-learning overshoot protection value (`4.2.1+xtreme.4`, 2026-10-21)

Switch: **Self-learning overshoot protection value (OPV)** (`xtreme_learned_opv`) with three modes:
*Off*, *Learn only* (the learned value is shown in a sensor, SAT keeps using the configured OPV) and
*Learn and apply* (SAT uses the learned value as the minimum setpoint and to decide when to use PWM).

**Why.** The OPV of the boiler is not fixed: it depends on how much heat the house takes at the
moment (room temperature, open or closed radiator valves). A fixed value is either too low (the
boiler overshoots and switches itself off) or too high (more heat than needed in every burn).

**How it learns** (`custom_components/sat/xtreme_opv.py`):

- A sample is only taken while the heating demand is on, the flame burns for at least 3 minutes,
  the modulation is at most 2 %, and there was no hot water in the last 5 minutes.
- **Plateau:** the flow temperature stays within 0.5 °C for 3 minutes, at least 0.5 °C below the
  setpoint. At minimum power the boiler cannot go lower, so this is a direct measurement of the OPV.
  It can move the estimate up and down; at most one plateau sample per burn.
- **Self shut-off:** the boiler switches itself off at minimum modulation while the heating demand is
  still on. The balance lies above this flow temperature, so this sample can only raise the
  estimate. Shut-offs caused by SAT (end of a PWM on phase) are ignored. Using the shut-off flow in
  both directions would be circular: in PWM mode the setpoint is the OPV itself.
- Update: `estimate += 0.1 × (sample − estimate)`, at most 1 °C per sample. The applied OPV is the
  estimate plus a margin of 1 °C, within 40–55 °C and never above the maximum setpoint.
- The estimate starts so that the applied value equals the configured OPV (or the result of the
  calibration of step 5), and is stored so it survives a restart.
- New sensor **Learned OPV** with the mode, estimate, margin, source, number of samples, last update
  and the last 20 samples as attributes.

**Files.** `custom_components/sat/xtreme_opv.py` (new), `custom_components/sat/xtreme_profile.py`,
`custom_components/sat/xtreme_sensor.py`, `custom_components/sat/const.py`,
`custom_components/sat/climate.py`, `custom_components/sat/coordinator.py`,
`custom_components/sat/config_flow.py`, `custom_components/sat/translations/en.json`,
`custom_components/sat/manifest.json`, `tests/test_xtreme_learned_opv.py` (new).

## Step 5: calibration for boilers that ignore the modulation limit (`4.2.1+xtreme.5`, 2026-10-21)

Switch: **Xtreme calibration** (`xtreme_calibration`). It adds the buttons **Start Xtreme
Calibration** and **Stop Xtreme Calibration**, a **Calibration** status sensor, and the actions
`sat.start_xtreme_calibration` and `sat.stop_xtreme_calibration`.

**Why.** The upstream calibration sets `MM=0` and computes `(100 − modulation) / 100 × setpoint`.
A boiler that ignores `MM=` keeps modulating, so the result is meaningless (for example 32 °C), and
it is still reported as successful. It also runs inside the configuration dialog, which does not
suit a measurement that takes hours.

**How it works** (`custom_components/sat/xtreme_calibration.py`):

- The thermostat must be in heat mode. While the calibration runs, SAT's own control loop does not
  send setpoints or heater commands. The calibration refreshes the control setpoint every 15
  seconds, so the gateway keeps the override and drops it as usual when Home Assistant stops.
- Each round starts at 55 °C (never above the maximum setpoint) once the anti-cycling time has
  passed. After each step it waits until the flow temperature is stable (within 0.5 °C for 5 minutes,
  flame on for at least 3 minutes) and then lowers the setpoint by 2 °C (modulation above 20 %) or
  1 °C. A step that is not stable within 30 minutes is recorded and the setpoint is lowered anyway.
- A round ends with a **plateau** (minimum modulation, stable flow at least 0.5 °C below the setpoint)
  or a **shut-off** (the boiler switches itself off at minimum modulation). A round that is still
  modulating at 35 °C, or gets no flame within 15 minutes, fails. Measurements below 35 °C are
  rejected.
- Hot water pauses the calibration and discards the current step; it continues once the
  anti-cycling time has passed. When the room is more than 1 °C above the target temperature the
  calibration pauses with the heating demand off until the room is back at the target.
- 5 valid rounds (at most 8 attempts), 20 minutes of cooldown between rounds, at most 10 hours in
  total. The result is the median. The calibration fails (and changes nothing) with fewer than 3
  valid rounds, a result below 35 °C or a spread of more than 6 °C.
- Stopping (button, action, turning the thermostat off, or a restart of Home Assistant) returns to
  normal operation immediately and changes nothing.
- A successful result becomes the starting value of the self-learning OPV (step 4), also when
  learning is off, so it is used as soon as learning is turned on. The configured OPV is not changed.
- The report (all rounds and steps, result, spread, minimum, maximum, duration) is shown in a
  notification and in the attributes of the Calibration sensor, and is stored across restarts.

**Files.** `custom_components/sat/xtreme_calibration.py` (new), `custom_components/sat/button.py`
(new), `custom_components/sat/xtreme_opv.py`, `custom_components/sat/xtreme_profile.py`,
`custom_components/sat/xtreme_sensor.py`, `custom_components/sat/const.py`,
`custom_components/sat/climate.py`, `custom_components/sat/__init__.py`,
`custom_components/sat/services.py`, `custom_components/sat/services.yaml`,
`custom_components/sat/config_flow.py`, `custom_components/sat/translations/en.json`,
`custom_components/sat/manifest.json`, `tests/test_xtreme_calibration.py` (new).

## Step 6: ready for Home Assistant 2026.12 (`4.2.1+xtreme.6`, 2026-10-21)

No switch: this change applies to everyone.

**Why.** Home Assistant logs *"Detected that custom integration 'sat' has an update listener and
should use it for scheduling a reload. This will stop working in Home Assistant 2026.12.0."*

**What changes.** The options flow is now an `OptionsFlowWithReload`, so Home Assistant reloads SAT
after the options are saved, and the update listener is removed. The minimum Home Assistant version
in `hacs.json` is raised to 2025.8.0, the first version with `OptionsFlowWithReload`.

**Files.** `custom_components/sat/__init__.py`, `custom_components/sat/config_flow.py`, `hacs.json`,
`custom_components/sat/manifest.json`, `tests/test_xtreme_reload.py` (new).
