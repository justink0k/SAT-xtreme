# SAT-xtreme manual

!!! warning "Unofficial fork"
    SAT-xtreme is an unofficial fork of [Smart Autotune Thermostat (SAT)](https://github.com/Alexwijn/SAT).
    All credit for SAT goes to its authors and contributors. Please do **not** report problems with this
    fork to the official SAT project; use [the issue tracker of this fork](https://github.com/justink0k/SAT-xtreme/issues).

SAT is a Home Assistant integration that controls a central heating boiler. Instead of switching the boiler
on and off like a classic thermostat, it decides **how warm the water in your radiators should be**, based
on the outside temperature (the heating curve) and on how far the room is from its target (a PID
controller).

SAT-xtreme is SAT with bug fixes and extra, **opt-in** features. Every feature has its own switch and is
off by default: with all switches off, it behaves like the official SAT 4.2.1 plus the bug fixes. The goal
is heating that is **calmer, more comfortable, more efficient and reliable**.

## Where to start

<div class="grid cards" markdown>

- **New to SAT?** Read [The control loop](how-sat-works.md) for the ideas, then
  [Installation](installation.md) and the [Setup wizard](setup-wizard.md).
- **Coming from the official SAT?** See [Moving from the official SAT](installation.md#moving-from-the-official-sat):
  your configuration, entity IDs and history are kept.
- **Want the fork features?** [First steps](first-steps.md) gives a safe order to turn them on, one at a
  time.
- **Something wrong?** See [Troubleshooting](troubleshooting.md).

</div>

## What the fork adds

| Feature | What it does | Page |
|---|---|---|
| Keep the setpoint ready | The boiler starts within seconds of a PWM block instead of waiting for the thermostat on the bus. | [Setpoint priming](prime-setpoint.md) |
| Ignore the modulation limit | For boilers that do not follow `MM=`; keeps the power sensor working. | [Ignore modulation limit](modulation-limit.md) |
| Align PWM with the boiler | Counts real burn time, waits for the anti-cycling time, longer minimum burn. | [Boiler timing](boiler-timing.md) |
| Self-learning OPV | Learns the overshoot protection value during normal heating. | [Learned OPV](learned-opv.md) |
| Calibration | A careful calibration of the OPV with start and stop buttons. | [Slow calibration](calibration.md) |
| PID settings | Gain factor, maximum rise above the heating curve, manual gains. | [PID settings](settings-pid.md) |
| Hand over to the thermostat | Gives control back to the thermostat on the bus right away when SAT is turned off. | [Hand over](handover.md) |
| Hot water keep-warm switch | Turns the keep-warm function off, for example at night. | [Hot water keep-warm](hot_water_keep_warm.md) |
| Boiler presets | Fills in the power and anti-cycling time of a known boiler. | [Boiler presets](boiler_presets.md) |
| Dashboard | A ready-made dashboard, created with one click. | [Dashboard](dashboard.md) |

Everything the fork adds is marked in Home Assistant: the options pages end in **(fork)** and the entities
start with **"Xtreme fork:"**.

## Tested setup

The features were developed for, and so far only tested on, one setup:

| | Tested setup |
|---|---|
| Boiler | Intergas Xtreme 30 (2024) |
| Gateway | OpenTherm Gateway, PIC firmware in gateway mode, controlled by SAT over MQTT |
| Thermostat on the bus | Nest with Heat Link, kept as a fallback when Home Assistant is down |

Other boilers and gateways that SAT supports should work, but have not been tested with the fork features.
Please report how it works for you (good or bad) on the issue tracker.

!!! danger "Use at your own risk"
    This software controls a central heating boiler, without any warranty. The license is GPL-3.0, the
    same as the official SAT.
