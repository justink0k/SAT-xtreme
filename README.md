> [!WARNING]
> **SAT-xtreme is an unofficial fork of [Smart Autotune Thermostat (SAT)](https://github.com/Alexwijn/SAT).**
> All credit for SAT goes to its authors and contributors. Thank you!
>
> Please do **not** report problems with this fork to the official SAT project.
> Use [the issue tracker of this fork](https://github.com/justink0k/SAT-xtreme/issues) instead.

## About SAT-xtreme

SAT-xtreme is SAT with fixes and extra, **opt-in** features. Every feature has its own switch and is
off by default: with all switches off, it behaves like upstream SAT 4.2.1 plus the bug fixes listed
below. The goal is a better SAT in general, while the official project has had no new commits since
March 2026.

### The goal: heating that is calmer, more comfortable, more efficient and reliable

SAT already decides how warm the water in your radiators should be, instead of switching the boiler
on and off. SAT-xtreme aims to make that work better in situations where SAT falls short, such as a
thermostat on the bus that passes the setpoint slowly, a boiler that ignores the modulation limit, or
the anti-cycling time of the boiler.

- **Calmer.** Fewer and longer burns instead of short bursts: the boiler starts right away when SAT asks
  for heat, every PWM block gets the burn time it was planned for, and SAT waits for the anti-cycling
  time of the boiler instead of asking for heat it cannot deliver yet. Optionally, the keep-warm
  function for hot water can be turned off (for example at night), which removes short hot water burns
  that restart the anti-cycling time. This is measurable on the dashboard: time from heating demand to
  flame, burn time per block and burner starts per day.
- **More comfortable, because you stay in control.**
  - Nothing changes behind your back: every feature has its own switch and is off by default, and a
    boiler preset only fills in numbers, it never turns a switch on.
  - You decide how SAT reacts: how strongly it corrects (gain factor), how far the water may get hotter
    than the heating curve (maximum rise), or your own PID values.
  - You can see why SAT does what it does: the heating curve, the PID correction, the burn time of each
    block, the remaining anti-cycling time, the learned overshoot protection value and the calibration
    report are sensors, and there is a ready-made dashboard.
  - Learning is transparent: the self-learning overshoot protection value first only shows what it
    learned, and SAT only uses it when you choose so. The calibration can be stopped at any moment and
    never heats the room more than 1 °C above your target.
- **More efficient (expected, still to be measured).** Every start of the boiler costs gas, because it
  starts at high power; fewer starts save gas. A correct overshoot protection value keeps the water as
  cool as possible, so the boiler condenses better. And no burn time is lost waiting for the setpoint.
  This has not been measured yet; a comparison of gas use per day will be added once it is.
- **Reliable.**
  - Your thermostat stays the fallback: when Home Assistant stops, the gateway drops the override and
    the thermostat on the bus takes over; when you turn SAT off, it can take over right away.
  - Hard limits: the maximum setpoint is never exceeded, also not during the calibration (upstream
    could), and hot water stays with the boiler (only the optional keep-warm switch, when you turn it
    off, stops the keep-warm function; hot water at the tap is not blocked on the tested boiler).
  - Commands arrive: SAT checks whether the boiler confirms the heating demand and sends it again when
    it does not (upstream could skip turning the demand off).
  - Safe to stop: the calibration stops cleanly on the stop button, when SAT is turned off and on a
    restart, and returns to normal operation right away.
  - Stable start-up: sensors and buttons no longer go missing at start-up, and SAT-xtreme is prepared
    for Home Assistant 2026.12.
  - Tested and reversible: every feature and fix has automated tests (upstream SAT 4.2.1: 7 tests), and
    every feature can be turned on and off on its own.

The features were developed for, and so far only tested on, one setup:

| | Tested setup |
|---|---|
| Boiler | Intergas Xtreme 30 (2024) |
| Gateway | OpenTherm Gateway, PIC firmware in gateway mode, controlled by SAT over MQTT |
| Thermostat on the bus | Nest with Heat Link, kept as a fallback when Home Assistant is down |

Other boilers and gateways that SAT supports should work too, but they have not been tested. If you
use SAT-xtreme with another setup, please report how it works (good or bad) on the issue tracker, and
consider [adding a boiler preset](https://justink0k.github.io/SAT-xtreme/boiler_presets/#adding-a-preset-for-your-boiler) for your boiler.

How the features work out on the tested setup, and the problems they solve, is described in
[Background and results](https://justink0k.github.io/SAT-xtreme/background/).

### SAT-xtreme compared to SAT

| | SAT 4.2.1 | SAT-xtreme | Switch |
|---|---|---|---|
| Setpoint in the PWM off phase | Drops to 10 °C. With a thermostat on the bus, the next setpoint reaches the boiler only with the next MsgID 1 of the thermostat (up to 150 s with a Nest). | Stays at the minimum setpoint with the heating demand off, so the boiler starts within seconds. | step 1 |
| Heating demand commands | Decided on the status bit of the boiler, which lags and may stay off while the boiler is anti-cycling, so `CH=0` can be skipped. | Decided on the last command, not repeated within 30 s, and resent when the boiler does not confirm it. | step 1 |
| Boilers that ignore the modulation limit | Keeps sending `MM=0` / `MM=100`. | Stops managing the limit (one neutral `MM=100`), keeps using the reported modulation. | step 2 |
| Power sensor | Only when the modulation limit is managed, and only when the boiler reports its capacity. | Also without a managed limit, with the rated power as fallback. | step 2 |
| PWM timing | The on time is wall-clock time from the heating demand; minimum on time 3 min; off phases can be shorter than the anti-cycling time of the boiler. | The on time counts burn time; a new block waits for the anti-cycling time after any flame, also short hot water flames; minimum burn and anti-cycling time are configurable. | step 3 |
| Overshoot protection value (OPV) | A fixed value. | Learned during normal operation, shown in a sensor, used only when you choose so. | step 4 |
| Calibration | Relies on `MM=0`, runs about 20 minutes in the setup wizard, can report a meaningless value (for example 32 °C) as successful, and could send a setpoint above the configured maximum. | First tests whether the boiler follows `MM=0`: if so, measures at minimum power (about 2 hours); if not, lowers the setpoint step by step (5 to 6 hours) and offers a one-click repair to turn on *ignore the modulation limit*. Median of 5 rounds, rejects unrealistic results, pauses for hot water and a too warm room, start/stop buttons and a report; never above the maximum setpoint. | step 5 (maximum: always) |
| PID strength | Only adjustable through the heating curve coefficient, which also moves the whole heating curve. The *Automatic gains* choice of the setup wizard was ignored. | Gain factor, maximum rise above the heating curve, and manual gains on their own page; the wizard choice is used. | PID page (wizard: always) |
| Hot water keep-warm | – (left to the boiler and the thermostat on the bus). | A switch to turn the keep-warm function off (`HW=0`) and back to normal (`HW=A`), by hand or with an automation. | keep-warm switch |
| Insight | – | Sensors for the boiler data (flow, setpoint, modulation, burner starts, flame, hot water, heating demand), the PID correction, PWM burn time, remaining anti-cycling time, learned OPV and calibration status. | boiler data and PID: always; the rest with the matching switches |
| Dashboard | – | The *SAT Xtreme* dashboard, created with one click from the entities that exist, with any gateway. | with one click |
| Turning SAT off | The thermostat on the bus takes over after the gateway heartbeat expires (about a minute). | Optionally right away (`CS=0`). | handover |
| Boiler presets | – | A preset list and a template to add your boiler. | preset |
| Home Assistant 2026.12 | Uses an update listener that will stop working. | Prepared: uses `OptionsFlowWithReload`. | always |
| Start-up | Sensors, binary sensors and buttons could be skipped (or fail with `KeyError: 'climate'`) when the climate was not ready yet. | The climate is set up first. | always |
| Recognisable in Home Assistant | – | Options pages end in "(fork)", entities start with "Xtreme fork:". | always |
| Automated tests | 7 | Every feature and fix has tests | – |

### What is changed

Everything the fork adds is marked as such in Home Assistant: the options pages end in **(fork)**
and the entities of the fork have names starting with **"Xtreme fork:"**. With all switches off and
the PID settings at their defaults, the fork behaves like upstream SAT. See
[CHANGES_XTREME.md](CHANGES_XTREME.md) for the details of every change, the files that were
modified, and how to go back to the official version.

| What | Where | Default |
|---|---|---|
| Step 1: prime the setpoint during the PWM off phase | *Configure → Xtreme profile (fork)* | off |
| Step 2: do not manage the modulation limit, rated power fallback | *Configure → Xtreme profile (fork)* | off |
| Step 3: align PWM with the boiler timing (burn time, anti-cycling, minimum burn) | *Configure → Xtreme profile (fork)* | off |
| Step 4: self-learning overshoot protection value (OPV) | *Configure → Xtreme profile (fork)* | off |
| Step 5: slow calibration of the OPV, with start/stop buttons | *Configure → Xtreme profile (fork)* | off |
| Step 6: prepared for Home Assistant 2026.12 | built in | always |
| Boiler preset: fills in the rated power and anti-cycling time of a known boiler ([how to add yours](https://justink0k.github.io/SAT-xtreme/boiler_presets/#adding-a-preset-for-your-boiler)) | *Configure → Xtreme profile (fork)* | Custom |
| Hand over to the thermostat right away when SAT is turned off (CS=0, OpenTherm Gateway via MQTT) | *Configure → Xtreme profile (fork)* | off |
| Hot water keep-warm switch: turn the boiler's keep-warm (comfort) function off, by hand or with an automation (HW=0 / HW=A, OpenTherm Gateway via MQTT) | *Configure → Xtreme profile (fork)* | off |
| PID settings: automatic gains, gain factor, maximum rise above the heating curve, manual gains | *Configure → PID settings (fork)* | unchanged |
| Dashboard *SAT Xtreme*, created with one click (see [Dashboard](https://justink0k.github.io/SAT-xtreme/dashboard/)) | *Settings → System → Repairs*, or the button *Xtreme fork: Create Dashboard* | not created until you click |

Entities of the fork (the PID output, boiler data and dashboard button always exist; the others only when the matching switch is on):

| Entity | Shows |
|---|---|
| *Xtreme fork: PID Output* | the PID correction on top of the heating curve, with the P, I and D parts and the gains in use |
| *Xtreme fork: PWM Burn Time* | burn time of the last PWM block, with the planned on time (step 3) |
| *Xtreme fork: Anti-cycling Remaining* | seconds until the boiler may start again (step 3) |
| *Xtreme fork: Learned OPV* | the learned OPV, with its samples (step 4) |
| *Xtreme fork: Calibration* | phase, progress and the last report of the calibration (step 5) |
| *Xtreme fork: Start Calibration*, *Xtreme fork: Stop Calibration* | buttons for the calibration (step 5) |
| *Xtreme fork: Boiler Flow*, *Control Setpoint*, *Boiler Modulation*, *Burner Starts* | boiler data as SAT sees it, for any gateway (burner starts are counted by SAT) |
| *Xtreme fork: Flame*, *Hot Water Active*, *Heating Demand* | boiler state as SAT sees it; heating demand is what SAT asks the boiler |
| *Xtreme fork: Create Dashboard* | button that creates or rebuilds the SAT Xtreme dashboard |
| *Xtreme fork: Hot Water Keep Warm* | switch: on = normal (`HW=A`: the DHW enable bit follows the thermostat on the bus, so keep-warm works as set on the boiler), off = no keep-warm (`HW=0`) |

Actions: `sat_xtreme.start_xtreme_calibration` and `sat_xtreme.stop_xtreme_calibration` (step 5).

#### Hot water keep-warm at night

The keep-warm switch turns the keep-warm (comfort) function of the boiler off, for example at night, to
avoid short hot water burns. Whether the boiler follows it depends on the boiler and its settings (on
Intergas: tap comfort on *Eco* and P074 = 0). See [Hot water keep-warm](https://justink0k.github.io/SAT-xtreme/hot_water_keep_warm/)
for an example automation and the details.

### Bug fixes

These fixes apply to everyone, without a switch:

- **Calibration above the maximum setpoint.** The calibration of upstream could send a control
  setpoint of 62 °C, above the configured maximum setpoint, when the boiler reports a higher maximum
  (MaxTSet). It now never exceeds the configured maximum.
- **Automatic gains in the setup wizard had no effect.** The wizard stored the choice (and manual kP,
  kI and kD) in the configuration data, while SAT reads it from the options, where automatic gains is
  on by default. The wizard now also writes these choices to the options, and they can be changed on
  the new *PID settings (fork)* page.
- **Prepared for Home Assistant 2026.12.** The update listener that Home Assistant 2026.12 no longer
  supports for reloading is replaced by `OptionsFlowWithReload`.
- **ESPHome: hot water and flame read from the right entities** (from upstream `develop`, `a590150` and
  `6ae78b4`). Hot water is now read from the `dhw_active` binary sensor (it used the hot water *enable*
  setting) and the flame from the binary sensor domain. ESPHome users need the `dhw_active` binary
  sensor in their ESPHome configuration (see the [ESPHome example](https://justink0k.github.io/SAT-xtreme/esphome/)).
- **Fixes from upstream `develop` that are not in a release yet:** the coordinator is fully set up
  before the calibration in the wizard starts (`7d43560`), the heater state command of EMS-ESP
  (`042dcca`), and turning the heater off when all valves close (`6e05470`).

- **Sensors or buttons missing after a restart.** All platforms were set up at the same time, while the
  sensors, binary sensors and buttons need the climate entity; when it was not ready yet, their entities
  were silently skipped (or failed with `KeyError: 'climate'`). The climate is now set up first.
- **Actions ignored a single entity.** `sat.reset_integral` and `sat.pulse_width_modulation` turned an
  entity ID given as text (as in most automations) into a list of letters, so they silently did nothing.
- **Home Assistant could hang during the setup calibration.** The calibration of upstream waited for the
  boiler temperature in a loop without a pause, which blocks Home Assistant when the temperature is
  missing. It now waits 15 seconds between checks.
- **Maximum cycles per hour counted per fixed hour.** The count started again every hour, so more starts
  than configured could follow each other around the turn of the hour. It now counts the last 60 minutes.
- **Stored dynamic minimum setpoint never loaded.** The base return temperature of the dynamic minimum
  setpoint was saved but never loaded after a restart. It is now loaded. This only matters when the
  dynamic minimum setpoint is on.
- **Synchronize with thermostat had no effect.** The option *Synchronize with thermostat attached to the
  boiler* (Presets page) was stored in the options but read from the configuration of the wizard. It now
  works; if you turned it on earlier, check that you still want it.
- **Simulation warning missing.** The option *Simulation* (Advanced page) was read from the wrong place by the
  thermostat, so the warning `Simulation mode!` never appeared in the log. Commands to the boiler were already
  correctly suppressed.
- **Dependency conflict with Home Assistant.** SAT required `pyotgw` 2.2.2, while Home Assistant itself uses
  2.2.3. It now requires at least 2.2.3, so it follows Home Assistant.
- **No error reports to the official SAT.** The option *Enable error monitoring* sent exceptions to the
  Sentry project of the official SAT. In the fork it would send the fork's errors there, so the option and
  Sentry are removed. Report problems as an
  [issue on GitHub](https://github.com/justink0k/SAT-xtreme/issues) instead.

See [CHANGES_XTREME.md](CHANGES_XTREME.md) for the files and versions of each fix.

### Installation (HACS)

1. In HACS, open *Custom repositories*, add `https://github.com/justink0k/SAT-xtreme` with type
   *Integration*, and install *SAT-xtreme*.
2. Restart Home Assistant and refresh the cache of your browser (Ctrl+Shift+R, or Cmd+Shift+R on a Mac).
3. Add the integration *SAT-xtreme* under *Settings → Devices & services*.
4. Create the dashboard: open *Settings → System → Repairs → Create the SAT Xtreme dashboard* and submit.
5. Enable the options you want, one at a time, under *Configure → Xtreme profile (fork)* and
   *Configure → PID settings (fork)*.

Since 4.2.1-xtreme.26, SAT-xtreme has its own domain, `sat_xtreme`. **Coming from the official SAT, or from
SAT-xtreme 4.2.1-xtreme.25 or older?** Choose *Move a configuration from SAT* when you add the integration:
all settings, entity IDs and their history are kept. See
[Moving from SAT](https://justink0k.github.io/SAT-xtreme/installation/#moving-from-sat).

### Dashboard

SAT-xtreme can create a **SAT Xtreme** dashboard with one click, from the entities that exist and with
any gateway. See [Dashboard](https://justink0k.github.io/SAT-xtreme/dashboard/).

### Documentation

The complete manual is at **[justink0k.github.io/SAT-xtreme](https://justink0k.github.io/SAT-xtreme/)**: how SAT
works, every gateway and setting, each fork feature, the entities and actions, and troubleshooting. Its
source is in [docs/](docs/).

### Disclaimer

Use at your own risk, without any warranty. This fork controls a central heating boiler. It has not
been tested with other boilers. The license (GPL-3.0) is unchanged; see [LICENSE](LICENSE).

