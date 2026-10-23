# General

*Configure → General*

## PID Controller Version

| Version | Name | Notes |
|---|---|---|
| 1 | Classic Controller | The original controller. Uses *Automatic Gains Value* and *Derivative Time Weight*. |
| 2 | Improved Controller | Uses *Automatic Gains Value* and *Derivative Time Weight*. |
| 3 | Adaptive Controller | **Default.** Calculates the gains from the heating curve; no further tuning needed. |

The fork's [PID settings](settings-pid.md) (gain factor, maximum rise) work with all versions.

## Minimum Setpoint Controller Version

Only shown when the [dynamic minimum setpoint](settings-advanced.md#dynamic-minimum-setpoint-experimental) is
on: *Return Temperature* (version 1) or *Boiler Temperature* (version 2).

## Heating Mode

Only shown when [rooms](setup-wizard.md#4-areas) are configured.

- **Comfort** (default): SAT looks at the error of every room and uses the largest one, so the coldest room
  decides how warm the water gets.
- **Eco**: SAT only uses the error of the main room.

## Maximum Setpoint

The highest water temperature SAT may ask for. Default 55 °C for radiators and heat pumps, 50 °C for
underfloor heating; the field allows 10 to 100 °C. For radiators, 55 to 75 °C is common; higher values
warm the house up faster but less efficiently. For underfloor heating stay at or below 50 °C.

!!! danger "A hard limit"
    SAT never sends a higher control setpoint than this, and the fork keeps to it as well, also during the
    [slow calibration](calibration.md). (The calibration of the official SAT 4.2.1 could exceed it.)

## Heating Curve Coefficient

How steep the [heating curve](how-sat-works.md#heating-curve) is: how much warmer the water gets when it
gets colder outside. Default 2.0, range 0.1 to 12.

How to tune it: watch the PID correction (*Xtreme fork: PID Output*) over a day or two with a steady target.

- The correction stays clearly **positive** (SAT keeps adding heat): the curve is too low; raise the
  coefficient a little, for example by 0.2.
- The correction stays clearly **negative**: the curve is too high; lower it.

Change it in small steps and wait a day in between. With [automatic gains](settings-pid.md#automatic-gains)
the PID strength follows the curve, so a good coefficient also gives a better PID.

## Automatic Gains Value and Derivative Time Weight

Only shown with automatic gains and PID controller version 1 or 2.

- **Automatic Gains Value** (default 2.0, range 1 to 5): how aggressive the automatic gains are. A good start
  is the same value as the heating curve coefficient.
- **Derivative Time Weight** (default 2.5, range 1 to 6): extra weight on the derivative (kD), which can
  reduce undershoot while warming up.

## Proportional, Integral and Derivative (kP, kI, kD)

Only shown when automatic gains is off. The fork's [PID settings](settings-pid.md) page is an easier place to
change these: it prefills them with the values SAT uses at that moment.

## Adjustment Factor for Return Temperature

Only shown with the [dynamic minimum setpoint](settings-advanced.md#dynamic-minimum-setpoint-experimental) on.
How strongly the minimum setpoint follows the return temperature. Default 0.2, range 0.1 to 0.5.

## Maximum Duty Cycle for Pulse Width Modulation

Only shown when *Automatic duty cycle* is off (see [System configuration](settings-system.md#automatic-duty-cycle)).
The length of one [PWM](overshoot-protection.md#pulse-width-modulation-pwm) block. Default 13 minutes.

## Contact Sensors

Door, window or garage door sensors. When one is open longer than the
[minimum open time](settings-system.md#minimum-time-for-window-to-be-open), SAT switches to the *Activity*
preset; when all are closed, it restores the previous target temperature. With contact sensors configured,
SAT adds a binary sensor *Window Sensor* that combines them.
