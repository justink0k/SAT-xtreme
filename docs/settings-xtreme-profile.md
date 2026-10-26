# Xtreme profile (fork)

*Configure → Xtreme profile (fork)*

All features of the fork, in five sections. Every option is **off** by default; with everything off, SAT
behaves like the official version. Turn on one option at a time and watch the effect for a few days (see
[First steps](first-steps.md)).

## Thermostat on the bus

For an OpenTherm Gateway with a thermostat (for example a Nest) still connected to the boiler.

| Option | Default | Details |
|---|---|---|
| Keep the setpoint ready between PWM blocks (setpoint priming) | off | [Setpoint priming](prime-setpoint.md) |
| Hand over to the thermostat when SAT is turned off | off | [Hand over](handover.md); OpenTherm Gateway over MQTT only |

## Boiler

Values for your boiler, from its rating plate and installation manual, or from a preset.

| Option | Default | Range | Details |
|---|---|---|---|
| Boiler preset | Custom | | [Boiler presets](boiler_presets.md) |
| The boiler ignores the modulation limit (ignore modulation limit) | off | | [Ignore modulation limit](modulation-limit.md) |
| Maximum heating output | 19.5 kW | 1 – 100 kW | Pn at 80/60 °C, maximum. Used for the power sensor when the boiler does not report its capacity. |
| Minimum heating output | 3.9 kW | 0.5 – 50 kW | Pn at 80/60 °C, minimum. Used for the power sensor when the boiler does not report its minimum. |
| Align PWM with the boiler (boiler timing) | off | | [Boiler timing](boiler-timing.md) |
| Anti-cycling time of the boiler | 300 s | 0 – 1800 s | How long the boiler waits before it starts again after switching off. |
| Extra margin on the anti-cycling time | 15 s | 0 – 120 s | Added to the anti-cycling time. |
| Minimum burn time per PWM block | 360 s | 240 – 600 s | The shortest burn of a block. |
| Do not heat below this duty cycle | 7.5 % | 2.5 – 30 % | Below this, SAT does not heat until the demand rises. |
| Hot water keep-warm switch | off | | [Hot water keep-warm](hot_water_keep_warm.md); OpenTherm Gateway over MQTT only |
| Maximum setpoint as an entity | off | | [Maximum setpoint entity](maximum-setpoint.md) |

!!! warning "Fill in your own boiler values"
    The defaults are the values of the tested Intergas Xtreme 30. Before you turn on *The boiler ignores the
    modulation limit* or *Align PWM with the boiler (boiler timing)*, enter the values of your own boiler or choose a matching
    preset.

The anti-cycling time, margin, minimum burn time and minimum duty cycle are only used with *Align PWM with the
boiler*. The heating outputs are only used with *The boiler ignores the modulation limit (ignore modulation limit)*.

## Learning and calibration

Find the [overshoot protection value](overshoot-protection.md#the-overshoot-protection-value-opv).

| Option | Default | Details |
|---|---|---|
| Self-learning OPV (learned OPV) | Off | *Off*, *Learn only* or *Learn and apply*; see [Learned OPV](learned-opv.md) |
| Lowest learned OPV | 40 °C | 30 – 55 °C; the learned OPV never goes below it |
| Search for the best OPV | off | See [Learned OPV](learned-opv.md#search-for-the-best-opv) |
| Gas meter (shown only) | none | Optional, for the search |
| Calibration buttons (slow calibration) | off | Adds the start and stop buttons and the status sensor; see [Slow calibration](calibration.md) |

## Sensors

What SAT does when the inside or outside temperature is no longer updated.

| Option | Default | Range | Details |
|---|---|---|---|
| Handle stale sensors | off | | See [Stale sensors](stale-sensors.md) |
| Maximum age of the inside temperature | 90 min | 10 – 1440 min | |
| Backup inside sensor | none | | Optional |
| Maximum age of the outside temperature | 180 min | 30 – 2880 min | |

## Diagnostics

Extra sensors to see what SAT does. They only read; they change nothing in the control.

| Option | Default | Details |
|---|---|---|
| Show the setpoint chain | off | Adds the sensor *Setpoint Chain*; see [Setpoint chain](setpoint-chain.md) |
| Track burner cycles | off | Records every burner cycle, with sensors, events and a history; see [Burner cycles](burner-cycles.md) |

## Where the options are stored

The options are stored with the other SAT options, so they survive updates and restarts. The official SAT
ignores them if you go back.
