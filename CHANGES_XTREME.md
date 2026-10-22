# Changes in SAT-xtreme

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

## Step 6: prepared for Home Assistant 2026.12 (`4.2.1+xtreme.6`, 2026-10-21)

No switch: this change applies to everyone.

**Why.** Home Assistant logs *"Detected that custom integration 'sat' has an update listener and
should use it for scheduling a reload. This will stop working in Home Assistant 2026.12.0."*

**What changes.** The options flow is now an `OptionsFlowWithReload`, so Home Assistant reloads SAT
after the options are saved, and the update listener is removed. The minimum Home Assistant version
in `hacs.json` is raised to 2025.8.0, the first version with `OptionsFlowWithReload`.

**Files.** `custom_components/sat/__init__.py`, `custom_components/sat/config_flow.py`, `hacs.json`,
`custom_components/sat/manifest.json`, `tests/test_xtreme_reload.py` (new).

## Step 7: dashboard (`4.2.1+xtreme.7`, 2026-10-21)

No switch: a dashboard template, no change to how SAT controls the boiler.

**What it adds.** `dashboards/sat_xtreme.yaml`, a dashboard made of standard Home Assistant cards
only:

- Now: the SAT thermostat, PWM phase and on/off time, the OPV in use, flame status, remaining
  anti-cycling time, modulation and power.
- Last 6 hours: control setpoint, flow, modulation, flame, heating demand and hot water. With step 1
  on, the setpoint is already up before the heating demand goes on.
- PWM blocks: burn time of the last block versus the planned on time, a 24-hour graph and burner
  starts per day.
- Learned OPV: value, mode, samples, last update and a 7-day graph.
- Calibration: start and stop buttons (with a confirmation), progress, and the last report.

The entity IDs at the top of the file must be replaced with your own. The cards for PWM, Learned OPV
and Calibration need the matching Xtreme profile switches.

**Files.** `dashboards/sat_xtreme.yaml` (new), `README.md`, `.gitignore` (ignores `local/` for
personal versions), `custom_components/sat/manifest.json`, `tests/test_xtreme_dashboard.py` (new).

## Step 8: PID settings and clear fork labels (`4.2.1+xtreme.8`, 2026-10-21)

New options page: **PID settings (fork)** (*Configure → PID settings (fork)*).

**Why.** SAT adds a PID correction to the heating curve. With automatic gains (PID version 3),
kP = heating curve coefficient × heating curve value ÷ 3, so the only way to make the correction
calmer was to lower the whole heating curve. Automatic gains could only be changed in the setup
wizard, and that choice was not even used (see the fix below).

**What changes.**

- **Automatic gains** can be switched on the new page. Switching it off opens a second page,
  **Manual gains (fork)**, with kP, kI and kD prefilled with the gains SAT uses at that moment, so
  saving them unchanged does not change the control.
- **Gain factor** (`xtreme_pid_gain_factor`, 0.3–1.5, default 1.0) multiplies the automatically
  calculated gains. It applies to kP, kI and kD alike: in PID version 3 kI and kD are derived from kP,
  so their ratios (how fast the integral acts, how early the derivative brakes) stay the same and
  only the strength changes. It has no effect on manual gains.
- **Maximum rise above the heating curve** (`xtreme_maximum_setpoint_rise`, 0–40 °C, default 0 = no
  limit): the requested setpoint never rises more than this above the heating curve. This also
  limits the morning warm-up. The maximum setpoint still applies on top of it.
- **Fix of an upstream bug:** the setup wizard stored *Automatic gains* and the manual kP, kI and kD in
  the configuration data, but SAT only reads them from the options (where automatic gains defaults to
  on). Turning automatic gains off in the wizard therefore had no effect. The wizard now also writes
  these choices to the options. Existing installations do not change until the wizard is run again
  or the new page is used.
- **Visibility:** new sensor **Xtreme fork: PID Output** (the correction in °C, with the heating curve,
  the requested setpoint, the P, I and D parts and the gains in use as attributes), and the climate
  entity has the attributes `automatic_gains`, `xtreme_pid_gain_factor`,
  `xtreme_maximum_setpoint_rise` and `pid_output` next to the existing `current_kp`, `current_ki` and
  `current_kd`.
- **Fork labels:** the options pages of the fork end in "(fork)" and start with a sentence that they
  belong to the unofficial fork. The entities of the fork have names starting with "Xtreme fork:".
  Entity IDs that already exist do not change; new entities get IDs with `xtreme_fork_` in them. The
  calibration actions and notification also mention the fork.
- The dashboard template has a new **PID (fork)** card and uses the new entity IDs. The README has an
  overview of everything the fork adds and where to find it.

**Files.** `custom_components/sat/pid.py`, `custom_components/sat/util.py`,
`custom_components/sat/climate.py`, `custom_components/sat/config_flow.py`,
`custom_components/sat/const.py`, `custom_components/sat/xtreme_profile.py`,
`custom_components/sat/xtreme_sensor.py`, `custom_components/sat/button.py`,
`custom_components/sat/xtreme_calibration.py`, `custom_components/sat/translations/en.json`,
`custom_components/sat/manifest.json`, `dashboards/sat_xtreme.yaml`, `README.md`,
`tests/test_xtreme_pid.py` (new), `tests/test_xtreme_dashboard.py`.

## Version 9: boiler preset, handover and two bug fixes (`4.2.1+xtreme.9`, 2026-10-21)

**Boiler preset** (`xtreme_boiler_preset`, *Configure → Xtreme profile (fork)*, default Custom). Fills in
the rated maximum and minimum heating power and the anti-cycling time of a known boiler. The first and
only preset is *Intergas Xtreme 30 (2024)*: 19.5 / 3.9 kW and 300 s (rating plate of a 2024 unit,
factory value of P036). A preset never turns a switch on or off. Choosing a preset fills in its values;
changing one of them by hand sets the preset back to Custom. When the preset is for another
manufacturer than the boiler reports, a warning is logged once. New presets come from users with the
boiler, through the *Boiler preset* issue template; `docs/boiler_presets.md` has the research notes and
the requirements.

**Hand over to the thermostat** (`xtreme_handover_on_off`, default off). When the SAT thermostat is
turned off, SAT sends `CS=0` once, so the OpenTherm Gateway hands the setpoint and the heating demand
back to the thermostat on the bus right away instead of after about a minute. If Home Assistant stops,
the heartbeat of the gateway still does this. Only for the OpenTherm Gateway over MQTT; other devices
ignore the switch.

**Bug fixes** (no switch):

- The climate platform is set up before the other platforms. They need the climate entity, and setting
  them up at the same time could skip their entities or fail with `KeyError: 'climate'`.
- The stored base return temperature of the dynamic minimum setpoint is loaded after a restart (upstream
  saved it but never loaded it). Only matters when the dynamic minimum setpoint is on.

**Files.** `custom_components/sat/xtreme_profile.py`, `custom_components/sat/const.py`,
`custom_components/sat/config_flow.py`, `custom_components/sat/climate.py`,
`custom_components/sat/coordinator.py`, `custom_components/sat/mqtt/opentherm.py`,
`custom_components/sat/__init__.py`, `custom_components/sat/translations/en.json`,
`custom_components/sat/manifest.json`, `docs/boiler_presets.md` (new),
`.github/ISSUE_TEMPLATE/boiler_preset.yml` (new), `README.md`,
`tests/test_xtreme_presets_and_handover.py` (new).

## Version 10: bug fixes (`4.2.1+xtreme.10`, 2026-10-21)

No switch: these are fixes.

- **Actions with a single entity** (upstream). `sat.reset_integral` and `sat.pulse_width_modulation`
  validated `entity_id` with `list[str]`, which turns a single entity ID given as text into a list of
  characters, so the action silently did nothing. They now use `cv.entity_ids`
  (`custom_components/sat/services.py`).
- **Setup calibration could hang Home Assistant** (upstream). While waiting for the boiler temperature,
  the calibration looped without a pause and blocked the event loop. It now sleeps 15 seconds between
  checks, so the time-out of the calibration can end it (`custom_components/sat/overshoot_protection.py`).
- **Anti-cycling wait after a restart** (fork, step 3 and the calibration). At start-up the flame
  statistics record the first "flame off" observation as a flame-off, so after every restart or options
  change the first PWM block waited the full anti-cycling time. Only a real flame-off now counts
  (`custom_components/sat/flame.py`, `custom_components/sat/coordinator.py`).
- **Maximum cycles per hour** (upstream). The count was reset every fixed hour instead of covering the
  last 60 minutes, so more starts than configured could follow each other around the turn of the hour
  (`custom_components/sat/pwm.py`).

**Files.** As listed above, plus `custom_components/sat/manifest.json`, `README.md` and
`tests/test_xtreme_bugfixes.py` (new).

**Display name** (same date): the integration is now shown as *SAT-xtreme* in HACS and Home Assistant
(was *SAT (Intergas Xtreme fork)*), to match the broader goal of the fork. The domain stays `sat`, so
existing configurations are kept (`custom_components/sat/manifest.json`, `hacs.json`, `README.md`,
`custom_components/sat/translations/en.json`, `dashboards/sat_xtreme.yaml`).

## Version 11: clearer options pages (`4.2.1+xtreme.11`, 2026-10-21)

No change to how SAT controls the boiler, and no change to the stored options.

- The *Xtreme profile (fork)* page is split into three groups: **Thermostat on the bus** (keep the
  setpoint ready, hand over), **Boiler** (preset, modulation limit, heating output, PWM timing,
  anti-cycling, burn time) and **Learning and calibration** (self-learning OPV, calibration). The values
  are still stored as the same flat options.
- All texts of the fork's options pages are rewritten for any boiler (no Intergas-specific wording
  outside examples) and every option has an explanation, including kP, kI and kD on the manual gains
  page. The boiler preset names are translatable.
- Dutch translation of all texts of the fork (`nl.json`); other languages fall back to English.

**Files.** `custom_components/sat/config_flow.py`, `custom_components/sat/translations/en.json`,
`custom_components/sat/translations/nl.json`, `custom_components/sat/manifest.json`,
`tests/xtreme_helpers.py`, `tests/test_xtreme_presets_and_handover.py`,
`tests/test_xtreme_prime_setpoint.py`, `tests/test_xtreme_reload.py`.

## Version 12: releases and a new version format (`4.2.1-xtreme.12`, 2026-10-21)

No change to how SAT controls the boiler.

- **New version format: `4.2.1-xtreme.N`** (was `4.2.1+xtreme.N`). Home Assistant and HACS compare
  versions with AwesomeVersion, which ignores everything after a `+` (semver build metadata), so
  `4.2.1+xtreme.12` would not count as newer than `4.2.1+xtreme.11`. With a `-`, `4.2.1-xtreme.12` is newer
  than `4.2.1-xtreme.11` (and `4.2.1-xtreme.10` newer than `4.2.1-xtreme.9`). AwesomeVersion does not treat
  it as a beta, and HACS only treats a release as a pre-release when it is marked as such on GitHub.
- **Releases.** This is the first version published as a GitHub release with a tag equal to the version
  in `manifest.json`, so HACS shows version numbers and offers updates. `RELEASING.md` describes the
  steps; `tests/test_version.py` checks the version format and that this file has an entry for it.
- **README corrections:** the tests are described without a number that goes out of date, Home
  Assistant 2026.12 support is described as "prepared for" (2026.12 is not released yet), and the
  installation explains refreshing the browser or app cache after an update.

**Files.** `custom_components/sat/manifest.json`, `CHANGES_XTREME.md`, `README.md`, `RELEASING.md` (new),
`CLAUDE.md` (new), `tests/test_version.py` (new).

## Version 13: hot water keep-warm switch (`4.2.1-xtreme.13`, 2026-10-21)

Option: **Hot water keep-warm switch** (`xtreme_hot_water_switch`, *Xtreme profile → Boiler*, default
off). OpenTherm Gateway over MQTT only.

**Why.** The keep-warm (comfort) function of a combi boiler fires the burner for a few seconds now and
then to keep the hot water ready. On the tested boiler that happened about three times per hour, and
every such burn starts the anti-cycling time, which also delays the next heating block. Some users want
keep-warm only during the day, or never.

**What it does.** With the option on, SAT adds the switch *Xtreme fork: Hot Water Keep Warm*:

- **On:** `HW=A`. The DHW enable bit is left to the thermostat on the bus, so the boiler keeps hot water
  warm as set on the boiler (comfort or eco). This is normal operation.
- **Off:** `HW=0`. The gateway clears the DHW enable bit. On the tested Intergas Xtreme 30 this stops
  keep-warm (no short hot water burns for three hours), while hot water still comes out of the tap
  (a tap of more than a minute worked normally); it only takes longer. Some boilers may block hot water
  completely when this bit is off, so this must be tested per boiler.
- The switch can be used by hand or in automations (an example is in the README). After a restart it
  restores its last state and sends it again.
- The gateway keeps `HW=` until it is changed (no heartbeat, also when Home Assistant is down). When the
  option is turned off while keep-warm was off, SAT sends `HW=A` once, so keep-warm is given back to
  the boiler. Removing SAT-xtreme while the switch is off leaves `HW=0` on the gateway; turn the switch
  on first.

This is an exception to "hot water stays with the boiler": it only changes keep-warm, only when the
user turns the option on and the switch off.

**Files.** `custom_components/sat/xtreme_switch.py` (new), `custom_components/sat/switch/__init__.py`
(platform entry), `custom_components/sat/__init__.py`, `custom_components/sat/const.py`,
`custom_components/sat/xtreme_profile.py`, `custom_components/sat/coordinator.py`,
`custom_components/sat/mqtt/opentherm.py`, `custom_components/sat/config_flow.py`,
`custom_components/sat/translations/en.json`, `custom_components/sat/translations/nl.json`,
`custom_components/sat/manifest.json`, `dashboards/sat_xtreme.yaml`, `README.md`,
`tests/test_xtreme_hot_water_switch.py` (new), `tests/test_xtreme_dashboard.py`.

## Version 14: modulation limit test in the calibration (`4.2.1-xtreme.14`, 2026-10-21)

Part of the **Xtreme calibration** option (step 5); no new option.

- **Test first.** Before the first round, the calibration sets the maximum modulation to 0 % (`MM=0`)
  and burns for a few minutes. It ignores the first minute of each burn (many boilers start at high
  power) and any time with hot water, and then looks at the reported modulation: at most 5 % means the
  boiler follows the limit, at least 20 % means it ignores it, anything else (or too few samples within
  15 minutes) is inconclusive. A boiler that does not report its modulation skips the test.
- **Faster rounds when the boiler follows the limit.** `MM=0` stays on, so every round burns at minimum
  power and the stable flow temperature is the measurement right away: one step per round instead of
  lowering the setpoint step by step. Still 5 rounds and the median, so the result stays as reliable;
  the calibration takes about 2 hours instead of 5 to 6. Other boilers use the step-down method as
  before. The normal limit (`MM=100`) is always restored after the test and at the end.
- **Repair instead of an automatic change.** When the boiler ignores the limit and the option *The
  boiler ignores the modulation limit* is off, SAT-xtreme creates a repair under *Settings → System →
  Repairs* with a fix button that turns the option on (and reloads SAT). Nothing changes without that
  click.
- The report and the notification show the result of the test; the option description gives an honest
  duration.

**Files.** `custom_components/sat/xtreme_calibration.py`, `custom_components/sat/repairs.py` (new),
`custom_components/sat/climate.py`, `custom_components/sat/xtreme_sensor.py`,
`custom_components/sat/translations/en.json`, `custom_components/sat/translations/nl.json`,
`custom_components/sat/manifest.json`, `tests/test_xtreme_calibration.py`.

## Version 15: dashboard with one click (`4.2.1-xtreme.15`, 2026-10-21)

No change to how SAT controls the boiler.

- **Boiler data from SAT itself.** New sensors *Xtreme fork: Boiler Flow*, *Control Setpoint*, *Boiler
  Modulation* and *Burner Starts* (counted by SAT, heating and hot water, kept across restarts), and
  binary sensors *Xtreme fork: Flame*, *Hot Water Active* and *Heating Demand* (what SAT asks the
  boiler). They show the data SAT already has, so the dashboard works with any gateway.
- **Dashboard builder** (`custom_components/sat/xtreme_dashboard.py`). Looks up the entities of this SAT
  entry by their unique IDs in the entity registry and builds the *SAT Xtreme* dashboard (icon
  `mdi:home-thermometer-outline`), leaving out cards of features that are off.
- **Created with one click, never automatically.** After setup, a repair *Create the SAT Xtreme
  dashboard* with a fix button; the button *Xtreme fork: Create Dashboard* and the action
  `sat.create_xtreme_dashboard` rebuild it later. Only the SAT Xtreme dashboard is ever changed.
- Creating a dashboard from an integration is not an official Home Assistant API (it uses the same
  storage collection as *Settings → Dashboards*). When that fails, the configuration is shown in a
  notification to paste by hand.

**Files.** `custom_components/sat/xtreme_dashboard.py` (new), `custom_components/sat/xtreme_binary_sensor.py`
(new), `custom_components/sat/xtreme_sensor.py`, `custom_components/sat/binary_sensor.py`,
`custom_components/sat/button.py`, `custom_components/sat/repairs.py`, `custom_components/sat/services.py`,
`custom_components/sat/services.yaml`, `custom_components/sat/flame.py`, `custom_components/sat/coordinator.py`,
`custom_components/sat/climate.py`, `custom_components/sat/__init__.py`, `custom_components/sat/const.py`,
`custom_components/sat/translations/en.json`, `custom_components/sat/translations/nl.json`,
`custom_components/sat/manifest.json`, `README.md`, `tests/test_xtreme_dashboard_builder.py` (new),
`tests/test_xtreme_pid.py`.

## Version 16: dashboard uses the gateway's sensors and follows the features (`4.2.1-xtreme.16`, 2026-10-21)

No change to how SAT controls the boiler.

- **Gateway sensors first.** With an OpenTherm Gateway over MQTT, the dashboard uses the gateway's own
  sensors for the control setpoint, flow, modulation, burner starts, flame, heating demand and hot water
  (unique IDs `<device>-pic_<label>` of the OTGW firmware 2.x, or `<device>-<label>` of older firmware).
  They have their full history and the real burner start counter of the boiler. Other gateways, or
  missing sensors, fall back to SAT-xtreme's own sensors.
- **The dashboard follows the features.** SAT-xtreme remembers a fingerprint of the dashboard it built.
  After every reload (for example after saving the options) it compares the dashboard with that
  fingerprint: when it is unchanged, it is rebuilt automatically with the cards of the features that are
  on now; when it was changed by hand, a repair *The SAT Xtreme dashboard can be updated* offers the
  rebuild with a fix button, and nothing is overwritten without that click.
- `lovelace` is an after-dependency, so dashboards are loaded before SAT checks them.
- The description of the hot water keep-warm option explains `HW=A` precisely: the DHW enable bit
  follows the thermostat on the bus.

**Files.** `custom_components/sat/xtreme_dashboard.py`, `custom_components/sat/repairs.py`,
`custom_components/sat/__init__.py`, `custom_components/sat/manifest.json`,
`custom_components/sat/translations/en.json`, `custom_components/sat/translations/nl.json`, `README.md`,
`tests/test_xtreme_dashboard_builder.py`.

## Version 17: keep-warm switch depends on the boiler settings (`4.2.1-xtreme.17`, 2026-10-22)

No change to how SAT controls the boiler; texts only.

- The description of the **hot water keep-warm switch** and the README now say that whether the boiler
  follows the DHW enable bit depends on the boiler. On Intergas, according to the Intergas manual,
  keep-warm can only be switched through OpenTherm when the tap comfort is set to *Eco* and parameter
  P074 (number of Eco days, factory value 7) is 0. With *On*, or with a self-learning *Eco*, the boiler
  ignores the bit and the switch has no effect.
- The README no longer presents the first `HW=0` test as a result: the tested boiler was set to *On*, so
  the fewer short hot water burns afterwards were most likely a coincidence. What still holds: hot water
  came out of the tap, and the gateway kept `HW=0` across restarts.
- `docs/boiler_presets.md` notes this condition for Intergas.

**Files.** `custom_components/sat/translations/en.json`, `custom_components/sat/translations/nl.json`,
`custom_components/sat/manifest.json`, `README.md`, `docs/boiler_presets.md`.
