# Changes in SAT-xtreme

This file lists every change of this fork compared to upstream
[Smart Autotune Thermostat (SAT)](https://github.com/Alexwijn/SAT), as required by the GPL-3.0
license: what was changed, in which files, and when.

The fork is based on upstream tag `4.2.1`.

Feature names: older entries call the features "step 1" to "step 5". Since version 29 they are called
**setpoint priming** (step 1), **ignore modulation limit** (step 2), **boiler timing** (step 3), **learned OPV**
(step 4) and **slow calibration** (step 5).

Folder and domain: entries before version 26 use the old folder `custom_components/sat` and the domain `sat`.
Since version 26 the integration lives in `custom_components/sat_xtreme` with the domain `sat_xtreme`.

## Switches

The switches live under *Settings → Devices & services → SAT-xtreme → Configure → Xtreme profile (fork)* and
*PID settings (fork)*.
They are stored as regular SAT options, so they survive updates and restarts. Every switch is **off**
by default; with all switches off the fork behaves like upstream SAT `4.2.1` plus the fixes listed
under "Base".

The constants and decision logic of the profile are in `custom_components/sat_xtreme/xtreme/profile.py`.
All decisions are logged at debug level with the prefix `Xtreme profile:`. To see them, add this to
`configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.sat_xtreme: debug
```

## Going back to the official SAT

1. If you use the hot water keep-warm switch, turn it **on** first, so the gateway does not keep keep-warm off.
2. Install the official *Smart Autotune Thermostat* from HACS and set it up again with the wizard. There is no
   automatic move back, because SAT-xtreme has its own domain (`sat_xtreme`).
3. Remove SAT-xtreme under *Settings → Devices & services* and in HACS, and restart Home Assistant.

See [Going back to the official SAT](https://justink0k.github.io/SAT-xtreme/installation/#going-back-to-the-official-sat)
in the manual.

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

**Files.** `custom_components/sat/xtreme/profile.py` (new), `custom_components/sat/const.py`,
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

**Files.** `custom_components/sat/xtreme/profile.py`, `custom_components/sat/const.py`,
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

**Files.** `custom_components/sat/xtreme/profile.py`, `custom_components/sat/xtreme_sensor.py` (new),
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

**Files.** `custom_components/sat/xtreme_opv.py` (new), `custom_components/sat/xtreme/profile.py`,
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
(new), `custom_components/sat/xtreme_opv.py`, `custom_components/sat/xtreme/profile.py`,
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
`custom_components/sat/const.py`, `custom_components/sat/xtreme/profile.py`,
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

**Files.** `custom_components/sat/xtreme/profile.py`, `custom_components/sat/const.py`,
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
`custom_components/sat/xtreme/profile.py`, `custom_components/sat/coordinator.py`,
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

## Version 18: merge of upstream develop (`4.2.1-xtreme.18`, 2026-10-22)

The fork is merged with upstream `develop` (last upstream commit 2026-03-01), so GitHub no longer
reports it as behind the official SAT and future upstream changes are easy to compare.

- **ESPHome fixes from upstream** (`a590150`, `6ae78b4`): hot water is read from the `dhw_active`
  binary sensor instead of the hot water *enable* setting, the flame from the binary sensor domain, and
  the ESPHome example in the README gains `dhw_active` and initial values for `t_dhw_set` and `t_set`.
  Does not affect the OpenTherm Gateway.
- The three upstream fixes that were already cherry-picked in the base (`7d43560`, `042dcca`, `6e05470`)
  are now part of the history as well; their content was already in the fork (the conflict in
  `climate.py` was resolved by keeping the fork's version, which contains `6e05470`).
- **Not taken over:** upstream's issue and pull request templates and the stale-issue workflow. They
  point to the official SAT, and the workflow would close issues (such as boiler preset requests)
  automatically.

**Files.** `custom_components/sat/esphome/__init__.py`, `README.md`, `custom_components/sat/manifest.json`,
`tests/test_esphome_upstream_fixes.py` (new).

## Version 19: no error reports to the official SAT (`4.2.1-xtreme.19`, 2026-10-22)

The option *Enable error monitoring* (off by default) sent exceptions to the Sentry project of the
official SAT, with a fixed address in the code. For SAT-xtreme this sent the fork's errors to the
maintainer of the official SAT, who cannot act on them, and users could think they were reporting to
this fork.

- The Sentry client, its fixed address and the option are removed. A stored `error_monitoring` value
  from an earlier version is ignored; nothing else changes.
- `sentry-sdk` is no longer a requirement, so Home Assistant has one package less to install.
- Report problems as an issue on GitHub instead.

**Files.** `custom_components/sat/__init__.py`, `custom_components/sat/const.py`,
`custom_components/sat/config_flow.py`, `custom_components/sat/manifest.json`,
`custom_components/sat/translations/*.json`, `requirements_test.txt`, `README.md`,
`tests/test_xtreme_no_error_reporting.py` (new).

**Repository housekeeping** (no effect on the integration):

- The GitHub workflows run on the `xtreme` branch: the HACS check and hassfest now run on every push
  (they waited for a `master` branch that the fork does not have), and the test workflow uses current
  versions of `actions/checkout` and `actions/setup-python`.
- The release workflow is removed: it built a zip file that was never attached to the release.
- The upstream development setup (`compose.yml`, `configuration.yaml`) moved to `dev/`, so the root no
  longer looks like configuration for users.
- `dashboards/sat_xtreme.yaml` and its test are removed. The *Create Dashboard* button builds the
  dashboard from the entities that exist (version 15 and 16), and the hand-written file had fallen behind
  it.

**Files.** `.github/workflows/hacs.yml`, `.github/workflows/hassfest.yml`, `.github/workflows/pytest.yml`,
`.github/workflows/release.yml` (removed), `dev/compose.yml`, `dev/configuration.yaml` (moved),
`dashboards/sat_xtreme.yaml` and `tests/test_xtreme_dashboard.py` (removed), `README.md`.

## Version 20: fork code in its own folder, documentation split up (`4.2.1-xtreme.20`, 2026-10-22)

No change in behaviour; the code and the documentation are reorganised.

- **The fork's own modules moved to `custom_components/sat/xtreme/`**, so it is clear at a glance what
  belongs to the fork: `xtreme_profile.py` → `xtreme/profile.py`, and the same for `opv`, `calibration`,
  `sensor`, `binary_sensor`, `switch` and `dashboard`. Entities, unique IDs, options and stored data are
  unchanged.
- **The README is shorter.** It keeps what a user needs first (what the fork is, the comparison with SAT,
  the switches and entities, bug fixes, installation); the rest moved to `docs/`:
  - `docs/background.md`: what the fork improves and the results on the tested setup;
  - `docs/hot_water_keep_warm.md`: the keep-warm switch, the example automation and the boiler settings;
  - `docs/dashboard.md`: the SAT Xtreme dashboard;
  - `docs/sat_configuration.md`: the documentation of the official SAT (without its installation
    section, which pointed to the official SAT).

**Files.** `custom_components/sat/xtreme/` (new; the seven `xtreme_*.py` modules moved),
`custom_components/sat/__init__.py`, `binary_sensor.py`, `button.py`, `climate.py`, `config_flow.py`,
`const.py`, `coordinator.py`, `pwm.py`, `repairs.py`, `sensor.py`, `services.py`, `switch/__init__.py`,
`util.py`, `custom_components/sat/manifest.json`, `README.md`, `docs/` (four new pages),
`docs/boiler_presets.md`, `tests/` (import paths).

## Version 21: the manual as a website (`4.2.1-xtreme.21`, 2026-10-22)

A complete manual, written from the code, published at <https://justink0k.github.io/SAT-xtreme/> with MkDocs
Material and GitHub Pages. No change in behaviour.

- **Contents:** installation and the setup wizard, how SAT works (heating curve, PID, OPV and PWM), the
  gateways (with the ESPHome configuration), every options page field by field with its default and range,
  one page per fork feature, the entities, actions and repairs, troubleshooting with the list of bug fixes,
  and development notes.
- `docs/sat_configuration.md` is replaced by these pages. The boiler presets page now starts with how to use
  a preset; the research notes follow.
- The README and the *Documentation* link of the integration in Home Assistant point to the manual.
- The workflow `.github/workflows/docs.yml` builds the manual with `mkdocs build --strict` (broken links and
  anchors fail the build) and publishes it on every push to `xtreme` that changes `docs/` or `mkdocs.yml`.
- `tests/test_xtreme_manual.py` checks that every fork option, fork entity, action and repair is described in
  the manual and that every page is in the navigation.
- Found while writing: the option *Synchronize with thermostat attached to the boiler* (Presets page) is
  stored in the options but read from the configuration of the wizard, so it has no effect. This is an
  upstream bug; the manual notes it, and it is not fixed in this version.

**Files.** `mkdocs.yml`, `requirements_docs.txt`, `.github/workflows/docs.yml`, `docs/` (new pages, `assets/`),
`docs/sat_configuration.md` (removed), `docs/boiler_presets.md`, `docs/background.md`,
`docs/hot_water_keep_warm.md`, `docs/dashboard.md`, `README.md`, `.gitignore`,
`custom_components/sat/manifest.json`, `tests/test_xtreme_manual.py` (new).

## Version 22: fixes found by hassfest and while writing the manual (`4.2.1-xtreme.22`, 2026-10-22)

No switch: these are bug fixes that apply to everyone. Hassfest now runs on every push (version 19) and
reported the first two; both were already in upstream SAT.

- **pyotgw 2.2.3.** SAT required `pyotgw==2.2.2`, while Home Assistant itself depends on `pyotgw==2.2.3` (for its
  own OpenTherm Gateway integration). The requirement is now 2.2.3; the difference is a small bug fix in
  pyotgw's reconnect handling, and SAT uses the same API.
- **No URL in the translations.** Home Assistant does not allow URLs in translation strings. The example
  address of the serial gateway (`socket://otgw.local:25238`) is now passed as a placeholder; the text on
  the page is unchanged.
- **Synchronize with thermostat works.** The option *Synchronize with thermostat attached to the boiler* on the
  Presets page was stored in the options, but SAT read it from the configuration data of the wizard, so it
  had no effect. SAT now reads the options, with the configuration data as a fallback for older entries.
  **Note:** if you turned the option on earlier, SAT now really sends your target temperature to the
  thermostat on the bus (`TC=` on an OpenTherm Gateway).

**Files.** `custom_components/sat/manifest.json`, `custom_components/sat/config_flow.py`,
`custom_components/sat/climate.py`, `custom_components/sat/translations/*.json`, `README.md`,
`docs/settings-presets.md`, `docs/troubleshooting.md`, `tests/test_xtreme_hassfest_fixes.py` (new).

## Version 23: pyotgw as a minimum version (`4.2.1-xtreme.23`, 2026-10-22)

No switch: a fix for everyone. Version 22 pinned `pyotgw==2.2.3`. Hassfest does not allow pinning a package
that Home Assistant itself depends on, because the integration would then block or break when Home Assistant
moves to a newer pyotgw. The requirement is now `pyotgw>=2.2.3`, so it follows Home Assistant.

**Files.** `custom_components/sat/manifest.json`, `README.md`, `docs/troubleshooting.md`,
`tests/test_xtreme_hassfest_fixes.py`.

## Version 24: simulation warning (`4.2.1-xtreme.24`, 2026-10-22)

No switch: a bug fix for everyone. The option *Simulation* on the Advanced page is stored in the options, but
the thermostat read it from the configuration data of the wizard (the same upstream bug as *Synchronize with
thermostat* in version 22). The coordinator already read the options, so commands to the boiler were correctly
suppressed in simulation; only the warning `Simulation mode!` in the log never appeared. The thermostat now
reads the options, with the configuration data as a fallback for older entries.

**Files.** `custom_components/sat/climate.py`, `custom_components/sat/manifest.json`, `README.md`,
`docs/settings-advanced.md`, `docs/troubleshooting.md`, `tests/test_xtreme_hassfest_fixes.py`.

## Version 25: notice about the move to `sat_xtreme` (`4.2.1-xtreme.25`, 2026-10-22)

A transition version. The next version, 4.2.1-xtreme.26, gives SAT-xtreme its own domain, `sat_xtreme`, so it
can be listed in HACS and installed next to the official SAT. This version only prepares users for that; the
control does not change.

- A notice under *Settings → System → Repairs*, "SAT-xtreme is moving to its own domain", explains the move
  (update, then *Add integration → SAT-xtreme → Move a configuration from SAT*, then remove the old entry and
  change `sat.` actions to `sat_xtreme.`) and links to the manual. It has no button and can be ignored. It is
  removed again in version 26.
- The manual describes the move (installation page) and the notice (repairs page).

**Files.** `custom_components/sat/xtreme/moving_notice.py` (new), `custom_components/sat/__init__.py`,
`custom_components/sat/translations/en.json`, `custom_components/sat/translations/nl.json`,
`custom_components/sat/manifest.json`, `docs/installation.md`, `docs/repairs.md`,
`tests/test_xtreme_moving_notice.py` (new).
## Version 26: its own domain, `sat_xtreme` (`4.2.1-xtreme.26`, 2026-10-22, pre-release only)

SAT-xtreme gets its own domain, so it can be added to the default list of HACS and can be installed next to
the official SAT. No switch: the domain applies to everyone.

- **The integration moved** from `custom_components/sat` to `custom_components/sat_xtreme`, and the domain in
  `manifest.json` is `sat_xtreme`. Actions are now `sat_xtreme.reset_integral`, `sat_xtreme.pulse_width_modulation`,
  `sat_xtreme.start_xtreme_calibration`, `sat_xtreme.stop_xtreme_calibration` and `sat_xtreme.create_xtreme_dashboard`.
- **Moving from SAT.** When a configuration of the domain `sat` exists (the official SAT, or SAT-xtreme
  4.2.1-xtreme.25 or older), *Add integration → SAT-xtreme* first offers **Move a configuration from SAT**. It
  unloads the old configuration, creates a new one with the same data and options, and, before the new
  entities are created, moves the entities and the device with Home Assistant's own migration helpers (entity
  IDs, unique IDs, history and restored states stay the same), copies the fork's stored data (learned OPV,
  calibration report, keep-warm state, dashboard fingerprint), removes the notice of version 25 and the old
  configuration. An
  interrupted move continues on the next start (`custom_components/sat_xtreme/xtreme/migration.py`).
- **An icon of its own** in `custom_components/sat_xtreme/brand/` (a flame with a thermometer, drawn by
  `dev/make_icon.py`), also used as the logo of the manual. The icon of the official SAT is no longer used.
- The manual, the README and `RELEASING.md` use the new domain, paths and action names; the installation page
  explains the move.
- `ManufacturerFactory` imports the manufacturers relative to its own package instead of a fixed
  `custom_components.sat` path.
- The notice of version 25 ("SAT-xtreme is moving to its own domain") is removed again; the move step
  replaces it.

**Files.** `custom_components/sat_xtreme/` (renamed from `custom_components/sat/`; `manifest.json`, `const.py`,
`services.yaml`, `__init__.py`, `config_flow.py`, `manufacturer.py`, `translations/en.json`,
`translations/nl.json`, `xtreme/migration.py` (new), `xtreme/moving_notice.py` (removed), `brand/` (new)), `dev/make_icon.py` (new),
`dev/configuration.yaml`, `mkdocs.yml`, `docs/`, `README.md`, `RELEASING.md`, `CLAUDE.md`, `tests/` (import paths,
`test_xtreme_migration.py` (new), `test_xtreme_moving_notice.py` (removed)).

## Version 27: what the HACS test showed (`4.2.1-xtreme.27`, 2026-10-23)

Version 26 was tested in a separate Home Assistant with HACS 2.0.5: HACS installed 4.2.1-xtreme.25, then
4.2.1-xtreme.26, and the configuration was moved. The move worked (all entities kept their IDs, the thermostat
kept its mode and target). Two things needed a change:

- **HACS leaves the old folder behind.** HACS installs the new version in `custom_components/sat_xtreme` and no
  longer tracks `custom_components/sat`, so the older SAT-xtreme stayed installed and appeared a second time
  under *Add integration*. Removing SAT-xtreme in HACS would remove the new version instead. After the move, a
  repair **"Remove the files of the older SAT-xtreme"** now offers to remove the old folder with one click. It
  only removes the folder when its manifest is an older SAT-xtreme (name `SAT-xtreme`, version
  `*-xtreme.*`) and no configuration of the domain `sat` is left; the official SAT is never touched.
- **HACS only sees the new domain after a restart.** While Home Assistant runs, HACS keeps the old folder name,
  and the update fails with "No manifest.json file found" (without harm: the old version keeps running). The
  manual, the README and the move step now say to restart Home Assistant before updating, and that SAT-xtreme
  users must not remove SAT-xtreme in HACS.

**Files.** `custom_components/sat_xtreme/xtreme/migration.py`, `custom_components/sat_xtreme/repairs.py`,
`custom_components/sat_xtreme/__init__.py`, `custom_components/sat_xtreme/translations/en.json`,
`custom_components/sat_xtreme/translations/nl.json`, `custom_components/sat_xtreme/manifest.json`, `README.md`,
`docs/installation.md`, `docs/repairs.md`, `tests/test_xtreme_migration.py`.

## Version 28: the move keeps the entities (`4.2.1-xtreme.28`, 2026-10-23)

No switch: bug fixes for everyone. The first real move (on Home Assistant 2026.10) showed that the move of
version 26 and 27 could lose the entities.

- **Entities move before the device.** When a config entry is removed from a device, Home Assistant removes
  the entities of that entry on that device right away. The move removed the old entry from the device first,
  so the entities were removed and SAT-xtreme created new ones: with another entity ID when the old one was
  renamed or contained an area, and without the restored state (the thermostat came back off at 7 °C). The
  entities now move first. The earlier tests did not see this because the recreated entities got the same IDs
  there; the tests now use renamed entities and check that the registry entries themselves are kept.
- **Ignored discoveries are skipped.** An ignored discovery of the official SAT is no longer offered as a
  configuration to move.
- **Only for moving from the official SAT.** The repair that removed the files of an older SAT-xtreme
  (version 27) and the clean-up of the notice of version 25 are removed again: they were only needed for the one
  installation that moved from an older SAT-xtreme, which is done. The manual and the move step now describe a
  new installation and the move from the official SAT.

**Files.** `custom_components/sat_xtreme/xtreme/migration.py`, `custom_components/sat_xtreme/repairs.py`,
`custom_components/sat_xtreme/__init__.py`, `custom_components/sat_xtreme/translations/en.json`,
`custom_components/sat_xtreme/translations/nl.json`, `custom_components/sat_xtreme/manifest.json`, `README.md`,
`docs/installation.md`, `docs/setup-wizard.md`, `docs/index.md`, `docs/repairs.md`, `docs/actions.md`,
`tests/test_xtreme_migration.py`.

## Version 29: a shorter README (`4.2.1-xtreme.29`, 2026-10-23)

No change in behaviour.

- **The README is rewritten** to about 800 words: what SAT-xtreme is and for whom, a chart of one measured
  PWM block, "Is this for you?", the supported gateways, a short comparison with SAT 4.2.1, installing and moving
  from the official SAT (with what to check afterwards), and links to the manual. The "Open in HACS" button is at
  the top. The remark about upstream commits and the comparison of test counts are gone.
- **The chart** (`docs/images/pwm-block.svg`) shows one PWM block with SAT 4.2.1 and with setpoint priming,
  from two blocks measured on 21 October 2026. It is drawn by `dev/make_pwm_chart.py` and works in the light and
  dark theme of GitHub.
- **Feature names** replace "step 1" to "step 5" in the README and the manual: setpoint priming, ignore
  modulation limit, boiler timing, learned OPV and slow calibration. The option labels keep their description
  and show the name between brackets, for example *Keep the setpoint ready between PWM blocks (setpoint
  priming)*.
- `dev/screenshot_dashboard.py` takes screenshots of the SAT Xtreme dashboard with Playwright (URL and token from
  environment variables); a dashboard screenshot for the README will follow later.
- **Nothing is lost:** the goals, the full comparison with SAT 4.2.1 and the list of supported hardware moved to
  the manual (background and gateways pages); the chart is also on the setpoint priming page.

**Files.** `README.md`, `dev/make_pwm_chart.py` (new), `dev/screenshot_dashboard.py` (new), `docs/images/pwm-block.svg` (new), `docs/background.md`,
`docs/gateways.md`, `docs/prime-setpoint.md` and the other pages of `docs/` (feature names), `mkdocs.yml`,
`custom_components/sat_xtreme/translations/en.json`, `custom_components/sat_xtreme/translations/nl.json`,
`custom_components/sat_xtreme/manifest.json`.

## Version 30: review fixes (`4.2.1-xtreme.30`, 2026-10-24)

Three points that the Home Assistant review of custom integrations often raises.

- **The Advanced page is always shown.** `show_advanced_options` is deprecated in Home Assistant and logged a
  warning. *Configure → Advanced Options* no longer needs *Advanced mode* in the user profile; nothing on the
  page changes.
- **The simulator is no longer in the setup wizard.** It was only offered with *Advanced mode*. It stays for
  development and the tests, and is started from Python with the source `simulator`.
- **No fixed area.** The SAT device no longer suggests the area "Living Room"; Home Assistant leaves the area
  empty, or keeps the area you chose before.
- **No test code in the integration.** The coordinator without a boiler (mode `fake`) moved from
  `custom_components/sat_xtreme/fake/` to `tests/fake_coordinator.py`; the tests add it to the coordinator
  factory themselves.

**Files.** `custom_components/sat_xtreme/config_flow.py`, `custom_components/sat_xtreme/entity.py`,
`custom_components/sat_xtreme/const.py`, `custom_components/sat_xtreme/coordinator.py`,
`custom_components/sat_xtreme/fake/__init__.py` (moved to `tests/fake_coordinator.py`),
`custom_components/sat_xtreme/manifest.json`, `tests/conftest.py`, `tests/const.py`, `tests/xtreme_helpers.py`
and the tests that import the test coordinator, `tests/test_xtreme_review_fixes.py` (new), `docs/settings.md`,
`docs/settings-advanced.md`, `docs/setup-wizard.md`, `docs/gateways.md`, `docs/development.md`.

## Version 31: an up-to-date introduction of this file (`4.2.1-xtreme.31`, 2026-10-24)

Documentation only; no change in behaviour.

- The introduction of this file now names the folder `custom_components/sat_xtreme`, the menu *SAT-xtreme →
  Configure* and the logger `custom_components.sat_xtreme`. A note says that entries before version 26 use the
  old folder and domain `sat`; those entries are left as they were.
- **Going back to the official SAT** now has the right steps: there is no automatic move back since SAT-xtreme
  has its own domain, so the official SAT is set up again with the wizard.

**Files.** `CHANGES_XTREME.md`, `custom_components/sat_xtreme/manifest.json`.

## Version 32: the manual is built with Zensical (`4.2.1-xtreme.32`, 2026-10-24)

No change in the integration.

- **Zensical** builds the manual instead of MkDocs with Material for MkDocs, which is in maintenance mode.
  Zensical is made by the same team and reads the same `mkdocs.yml`; the pages, their text and the checks of
  links and anchors are the same. The manual gets the new look of Zensical.
- Zensical is **not pinned**, so the manual follows new versions. When a new version breaks the build, the
  workflow stops before publishing and the manual online stays as it was.
- The build check on pull requests also runs when `requirements_docs.txt` changes.

**Files.** `requirements_docs.txt`, `.github/workflows/docs.yml`, `docs/development.md`,
`custom_components/sat_xtreme/manifest.json`.

## Version 33: four ideas from the upstream cycle refactor (`4.2.1-xtreme.33`, 2026-10-24)

Four new options, all off by default; with them off, SAT-xtreme behaves as in version 32. The ideas come from
the closed upstream pull request [Alexwijn/SAT#124](https://github.com/Alexwijn/SAT/pull/124); the refactor
itself was not taken over, and no code was copied.

### Setpoint chain sensor (diagnostics)

A new option, off by default: *Xtreme profile (fork) → Diagnostics → Show the setpoint chain*. Read only; with
the option off, nothing changes.

- **The sensor *Xtreme fork: Setpoint Chain*** shows the setpoint SAT calculates (heating curve plus PID). Its
  attributes show the filtered setpoint, the control setpoint SAT sent to the gateway last (after PWM, setpoint
  priming and the maximum setpoint) with its time, the heating demand SAT sent, the control setpoint the
  gateway reports for the boiler (`TSet` on the OpenTherm Gateway), the difference between the two, and the
  PWM phase.
- The coordinator now remembers the last control setpoint it sent and when; it is only read by this sensor.
- The Xtreme profile page has a fourth section, *Diagnostics*.
- **Source of the idea:** the "requested setpoint" sensor of the closed upstream pull request
  [Alexwijn/SAT#124](https://github.com/Alexwijn/SAT/pull/124) (GPL-3.0). No code was taken from it; the fork's
  sensor also shows the sent and received setpoint.

**Files.** `custom_components/sat_xtreme/xtreme/sensor.py`, `custom_components/sat_xtreme/xtreme/profile.py`,
`custom_components/sat_xtreme/coordinator.py`, `custom_components/sat_xtreme/climate.py` (the property
`calculated_setpoint`), `custom_components/sat_xtreme/config_flow.py`, `custom_components/sat_xtreme/const.py`,
`custom_components/sat_xtreme/translations/en.json`, `custom_components/sat_xtreme/translations/nl.json`,
`tests/test_xtreme_setpoint_chain.py` (new), `tests/xtreme_helpers.py`, `tests/test_xtreme_presets_and_handover.py`,
`docs/setpoint-chain.md` (new), `docs/settings-xtreme-profile.md`, `docs/entities.md`, `mkdocs.yml`.

### Burner cycle diagnostics

A new option, off by default: *Xtreme profile (fork) → Diagnostics → Track burner cycles*. Read only; with the
option off, nothing is tracked, no events are fired and no file is written. The learned OPV and boiler timing do
not use it.

- **Every burner cycle** (flame on to flame off) is recorded with its start, end and duration, the flow
  temperature at the start and its minimum, maximum and time-weighted average, the return temperature at the
  start and end, the control setpoint at the start and end, the kind (`heating`, `hot_water`, `mixed`), the
  reason it ended (`hot_water`, `pwm_block_ended`, `no_heating_demand`, `setpoint_reached` with a margin of
  2 °C, `unknown`) and whether it started within the anti-cycling time. Short cycles are recorded too; a
  cycle running during a restart is not.
- **Events** `sat_xtreme_cycle_started` and `sat_xtreme_cycle_ended`.
- **Sensors** *Last Cycle*, *Cycles Last Hour*, *Cycles Last 24h*, *Average Burn Time Last Hour* and
  *Average Burn Time Last 24h*; the counters count all cycles and split them by kind in their attributes.
- **History** of the last 500 cycles in the Home Assistant store `sat_xtreme_cycles_<entry_id>`, kept across
  restarts and moved along when a configuration is moved.
- **Source of the idea:** the cycle tracking of the closed upstream pull request
  [Alexwijn/SAT#124](https://github.com/Alexwijn/SAT/pull/124) (GPL-3.0). No code was taken from it; the
  fork's module records other data, keeps a history and does not classify cycles for the control.

**Files.** `custom_components/sat_xtreme/xtreme/cycles.py` (new), `custom_components/sat_xtreme/xtreme/sensor.py`,
`custom_components/sat_xtreme/xtreme/profile.py`, `custom_components/sat_xtreme/xtreme/migration.py`,
`custom_components/sat_xtreme/config_flow.py`, `custom_components/sat_xtreme/const.py`,
`custom_components/sat_xtreme/translations/en.json`, `custom_components/sat_xtreme/translations/nl.json`,
`tests/test_xtreme_cycles.py` (new), `tests/test_xtreme_setpoint_chain.py`, `tests/xtreme_helpers.py`,
`docs/burner-cycles.md` (new), `docs/settings-xtreme-profile.md`, `docs/entities.md`, `docs/actions.md`,
`mkdocs.yml`.

### Maximum setpoint entity

A new option, off by default: *Xtreme profile (fork) → Boiler → Maximum setpoint as an entity*. With the option
off, nothing changes.

- **The number entity *Xtreme fork: Maximum Setpoint*** changes the maximum setpoint from a dashboard or an
  automation. A change is stored as the option *Maximum Setpoint* and used right away without a reload: the
  coordinator uses the new value and sends it to the gateway (`SH=` on the OpenTherm Gateway).
- **Limits:** at least the OPV in use (the learned OPV when applied, otherwise the configured one) and 30 °C; at
  most 75 °C for radiators, 50 °C for underfloor heating and 55 °C for a heat pump (the default maximum of
  SAT for an unknown heating system), and never above the upper bound the boiler reports in OpenTherm message
  49. Changes are refused while the slow calibration runs.
- The OpenTherm Gateway over MQTT now also reads `MaxTSetUBMaxTSetLB_value_hb` (message 49) when the gateway
  publishes it; nothing else uses it.
- **Source of the idea:** the maximum setpoint number of the closed upstream pull request
  [Alexwijn/SAT#124](https://github.com/Alexwijn/SAT/pull/124) (GPL-3.0). No code was taken from it; the fork's
  entity stores the value as the option and has other limits.

**Files.** `custom_components/sat_xtreme/xtreme/number.py` (new), `custom_components/sat_xtreme/number.py`,
`custom_components/sat_xtreme/coordinator.py`, `custom_components/sat_xtreme/mqtt/opentherm.py`,
`custom_components/sat_xtreme/xtreme/profile.py`, `custom_components/sat_xtreme/config_flow.py`,
`custom_components/sat_xtreme/const.py`, `custom_components/sat_xtreme/translations/en.json`,
`custom_components/sat_xtreme/translations/nl.json`, `tests/test_xtreme_maximum_setpoint.py` (new),
`docs/maximum-setpoint.md` (new), `docs/settings-xtreme-profile.md`, `docs/entities.md`, `mkdocs.yml`.

### Stale sensors

A new section *Sensors* on the Xtreme profile page, with the option *Handle stale sensors*, off by default.
With the option off, nothing changes and the *Temperature sensor maximum value age* of SAT works as before.

- **The age of a sensor** counts from its last report (`last_reported`, with `last_updated` as fallback), so a
  sensor that reports the same value is not seen as stale. *Unavailable* and *unknown* are not usable. The
  sensors are checked every minute. For the inside and outside sensor this replaces the maximum value age check
  of SAT, including its reset of the PID controller.
- **Inside temperature:** after *Maximum age of the inside temperature* (default 90 minutes) SAT uses the
  optional *Backup inside sensor* when it is up to date. Without a usable inside sensor SAT heats on the heating
  curve only, without the PID correction, and never above the setpoint it requested at that moment; the PID
  controller is left as it is. SAT returns to normal by itself when a sensor reports again.
- **Outside temperature:** after *Maximum age of the outside temperature* (default 3 hours) SAT uses the last
  known value.
- **The binary sensor *Xtreme fork: Stale Sensor*** and the repairs *The inside temperature of {name} is stale*
  and *The outside temperature of {name} is stale* show it while it lasts.
- **Source of the idea:** the stale sensor handling of the closed upstream pull request
  [Alexwijn/SAT#124](https://github.com/Alexwijn/SAT/pull/124) (GPL-3.0), which reset the PID controller and
  skipped the control. No code was taken from it; the fork uses a backup sensor and a safe mode instead.

**Files.** `custom_components/sat_xtreme/xtreme/stale.py` (new), `custom_components/sat_xtreme/climate.py`,
`custom_components/sat_xtreme/xtreme/binary_sensor.py`, `custom_components/sat_xtreme/xtreme/profile.py`,
`custom_components/sat_xtreme/config_flow.py`, `custom_components/sat_xtreme/const.py`,
`custom_components/sat_xtreme/translations/en.json`, `custom_components/sat_xtreme/translations/nl.json`,
`tests/test_xtreme_stale_sensors.py` (new), `tests/xtreme_helpers.py`, `tests/test_xtreme_presets_and_handover.py`,
`docs/stale-sensors.md` (new), `docs/settings-xtreme-profile.md`, `docs/settings-system.md`, `docs/entities.md`,
`docs/repairs.md`, `mkdocs.yml`, `custom_components/sat_xtreme/manifest.json`.

## Version 34: the learned OPV in practice (`4.2.1-xtreme.34`, 2026-10-26)

The self-learning OPV now learns per boiler, no longer runs away to the maximum, and can search for the best
OPV when there is nothing to measure. Everything only matters with the learned OPV on; the search is a new
option, off by default.

### The learned OPV learns in practice

The self-learning OPV (*learned OPV*) found no samples on boilers that report 10 % or more at their minimum
power, and would have pushed itself up once it did. Both only matter with the learned OPV on (*Learn only* or
*Learn and apply*).

- **Minimum modulation per boiler.** Instead of a fixed 2 %, the limit is the 10th percentile of the modulation
  reported during heating burns in the last 7 days (without the first 5 minutes of a burn and without hot
  water) plus 5 percentage points, and never below the minimum modulation the boiler reports (message 15).
  Until there are 30 values, 2 % is used. The learned limit is at most 30 %, unless the boiler reports a higher
  minimum itself. The values are stored with the learned OPV.
- **Fix: no runaway through the self shut-off.** A self shut-off only counts when the flow stayed more than
  0.5 °C below the setpoint. In PWM the setpoint is the OPV itself, so a shut-off at the setpoint plus the
  boiler's hysteresis raised the OPV, then the setpoint, then the next shut-off, up to the maximum.
- **The usual shut-off point is learned per boiler,** for boilers that switch off a little before the setpoint:
  the median of the flow minus the setpoint at the last 20 heating shut-offs. From 5 shut-offs on, a shut-off
  only counts when the flow stayed more than 2 °C below that point. Stored with the learned OPV.
- **New option *Lowest learned OPV*** (default 40 °C, the old fixed value; 30 to 55 °C).
- **New attributes** on *Learned OPV*: `minimum`, `modulation_limit`, `modulation_samples`,
  `shut_off_offset`, `shut_off_offset_samples` and `last_burn_result` (the sample of the last burn, or why it
  gave none).
- The manual notes that these rules have only been tested on an Intergas Xtreme 30 and asks for reports.

**Files.** `custom_components/sat_xtreme/xtreme/opv.py`, `custom_components/sat_xtreme/climate.py`,
`custom_components/sat_xtreme/xtreme/profile.py`, `custom_components/sat_xtreme/config_flow.py`,
`custom_components/sat_xtreme/const.py`, `custom_components/sat_xtreme/translations/en.json`,
`custom_components/sat_xtreme/translations/nl.json`, `tests/test_xtreme_learned_opv.py`, `tests/xtreme_helpers.py`,
`docs/learned-opv.md`, `docs/settings-xtreme-profile.md`.

### Search for the best OPV

A new option, off by default: *Learning and calibration → Search for the best OPV*, with an optional gas meter
that is only shown. It changes the setpoint only with the learned OPV on *Learn and apply*; with *Learn only* it
measures and shows the step it would take.

- **When:** after 3 days without a plateau sample, for houses where the boiler gives more heat at its minimum
  than the house takes, so the OPV cannot be measured.
- **Score:** heating starts per degree hour over a period of 48 hours, with at least 20 starts and 12 stable
  hours, otherwise the period is extended.
- **Comfort,** only in stable hours (target unchanged for at least 3 hours, heating on): not more than 0.5 °C
  too cold on average, and a spread around the target that does not grow by more than 50 % and 0.1 °C.
- **Steps of 1 °C:** a step down is kept when the score is not more than 15 % worse; a step up only when it is
  at least 15 % better; otherwise back, and after a search without gain 7 days of rest. Too cold during a trial
  ends it right away. Always between the lowest learned OPV, 55 °C and the maximum setpoint; a plateau sample
  ends the search.
- **Attributes** on *Learned OPV* with the phase, the value, the scores, the comfort of baseline and trial, the
  period and the last decision; the state is stored with the learned OPV.

**Files.** `custom_components/sat_xtreme/xtreme/opv_search.py` (new), `custom_components/sat_xtreme/xtreme/opv.py`,
`custom_components/sat_xtreme/climate.py`, `custom_components/sat_xtreme/xtreme/profile.py`,
`custom_components/sat_xtreme/config_flow.py`, `custom_components/sat_xtreme/const.py`,
`custom_components/sat_xtreme/translations/en.json`, `custom_components/sat_xtreme/translations/nl.json`,
`tests/test_xtreme_opv_search.py` (new), `tests/xtreme_helpers.py`, `docs/learned-opv.md`,
`docs/settings-xtreme-profile.md`, `custom_components/sat_xtreme/manifest.json`.

## Version 35: the new options on the dashboard (`4.2.1-xtreme.35`, 2026-10-26)

The SAT Xtreme dashboard shows the options of versions 33 and 34. An unchanged dashboard is updated by itself;
a dashboard changed by hand gets the repair that offers the update.

- **Learned OPV:** the card also shows the lowest OPV, the minimum modulation and how many values it is based
  on, the usual shut-off point and the result of the last burn.
- **OPV search** (new card, only with *Search for the best OPV* on): phase, value tried, step, next and last
  decision, starts per degree hour, spread and mean deviation of baseline and trial, stable hours and starts of
  the current period, and the gas use per degree hour.
- **Setpoint chain, Burner cycles and Sensors** (new cards, each only with its option on), and the
  *Maximum setpoint* in the card *Now*.
- The attribute `next_decision` of *Learned OPV* is now a date and time instead of a Unix time.

**Files.** `custom_components/sat_xtreme/xtreme/dashboard.py`, `custom_components/sat_xtreme/xtreme/opv_search.py`,
`custom_components/sat_xtreme/manifest.json`, `tests/test_xtreme_dashboard_builder.py`,
`tests/test_xtreme_opv_search.py`, `docs/dashboard.md`, `docs/learned-opv.md`.

## Unreleased: review of the learned OPV and the OPV search

From a review of version 35. Only matters with the learned OPV on.

- **Minimum modulation per burn.** Every heating burn gives one value, the lowest modulation after the first
  minute that two readings in a row reach, instead of one value per minute after the first 5 minutes. Short
  burns now count, and every burn weighs the same. The values per minute of versions 34 and 35 are dropped
  when the learned OPV is loaded; the limit is 2 % again until there are 30 burns. The estimate, the samples,
  the usual shut-off point and the state of the search are kept. The attribute `modulation_samples` is now
  `modulation_burns`.
- The OPV search of versions 34 and 35 is replaced by a model of the burn; see the next entry.

**Files.** `custom_components/sat_xtreme/xtreme/opv.py`, `custom_components/sat_xtreme/xtreme/dashboard.py`,
`tests/test_xtreme_learned_opv.py`, `tests/test_xtreme_dashboard_builder.py`, `docs/learned-opv.md`,
`docs/dashboard.md`.

## Unreleased: choose the OPV from a model of the burn

The option *Search for the best OPV* of versions 34 and 35 becomes *Choose the OPV from a model* (same stored
option, off by default). On the tested house the starts per degree hour varied about 50 % from day to day at the
same OPV, so trying a step and comparing periods could not decide within weeks. The model predicts instead.

- **The model:** per heating burn, the time from ignition to every whole degree of flow; per degree the median over
  the last 7 days; above the measured curve extended for at most 3 °C towards a balance temperature (shown as an
  estimate of the real OPV). The predicted burn time at an OPV is the time to the OPV plus the usual shut-off point.
  After every burn the prediction is compared with the real burn time.
- **The choice:** the lowest OPV with a predicted burn time of at least the *Minimum burn time per PWM block* of
  boiler timing, within the lowest learned OPV, 55 °C and the maximum setpoint; at most 1 °C per day, only with
  *Learn and apply*; back and 7 days blocked when the comfort gets worse in the 48 hours after a change.
- **Only when it applies:** at least 30 burns, at least 60 % of the heating burns ended by the boiler itself, at
  least 50 % of the heating time in PWM, a flow temperature, no heat pump, and a median prediction error of at most
  20 % over the last 24 hours. The attribute `model_status` says which.
- **New action `sat_xtreme.try_opv_offset`:** the OPV −3 to +3 °C for 1 to 72 hours, also with *Learn only*, to
  compare predicted and real burn times.
- **Dashboard:** the card *OPV search* becomes *OPV model*, with a card *Predicted burn time*.
- **Migration:** the stored state of the search is not read; a running search step ends. The model starts collecting
  burns (about 30, a day or two).

**Files.** `custom_components/sat_xtreme/xtreme/opv_model.py` (new), `custom_components/sat_xtreme/xtreme/opv_search.py`
(removed), `custom_components/sat_xtreme/xtreme/opv.py`, `custom_components/sat_xtreme/climate.py`,
`custom_components/sat_xtreme/services.py`, `custom_components/sat_xtreme/services.yaml`,
`custom_components/sat_xtreme/const.py`, `custom_components/sat_xtreme/xtreme/dashboard.py`,
`custom_components/sat_xtreme/translations/en.json`, `custom_components/sat_xtreme/translations/nl.json`,
`tests/test_xtreme_opv_model.py` (new), `tests/test_xtreme_opv_search.py` (removed),
`tests/test_xtreme_dashboard_builder.py`, `docs/learned-opv.md`, `docs/actions.md`, `docs/dashboard.md`,
`docs/settings-xtreme-profile.md`.
