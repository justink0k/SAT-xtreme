# Align PWM with the boiler

*Xtreme profile (fork) → Boiler → Align PWM with the boiler.* Default off.

## The problem

In the official SAT, the on time of a [PWM](overshoot-protection.md#pulse-width-modulation-pwm) block counts
from the moment SAT asks for heat, not from the moment the boiler burns. A boiler that starts late (because it
is still anti-cycling, or because the setpoint arrives late) burns shorter than planned. The pause between two
blocks can also be shorter than the anti-cycling time of the boiler, so SAT asks for heat the boiler cannot
deliver yet. And a short hot water tap restarts the anti-cycling time, which SAT does not know about.

## What the option does

- **Burn time instead of wall-clock time.** The on time of a block only counts while the flame burns for
  heating (not for hot water). If no flame appears within the anti-cycling time plus the margin plus 15
  seconds, the time counts anyway, so a block never waits forever; and a block never lasts longer than twice the planned on time
  plus that wait.
- **Wait for the anti-cycling time.** A new block only starts when the anti-cycling time (plus the margin) has
  passed since the **last flame**, also a short hot water flame, and when no hot water is being made.
- **Longer minimum burn.** Every burn lasts at least the *minimum burn time* (default 6 minutes instead of
  3). At a low demand SAT makes the pause longer rather than the burn shorter.
- **No heating at a very low demand.** Below the *minimum duty cycle* (default 7.5 %), SAT does not start a
  block until the demand rises.

## Settings

All on the [Xtreme profile page](settings-xtreme-profile.md#boiler), and only used with this option on:

| Setting | Default | Where to find your value |
|---|---|---|
| Anti-cycling time of the boiler | 300 s | The installation manual, for example parameter P036 on Intergas or HG09 on Wolf. See [Boiler presets](boiler_presets.md) for researched values. |
| Extra margin on the anti-cycling time | 15 s | Keep the default. |
| Minimum burn time per PWM block | 360 s | Longer means fewer starts and longer pauses. |
| Do not heat below this duty cycle | 7.5 % | Lower to heat more often at a very low demand. |

!!! tip
    Fill in the anti-cycling time **before** you turn the option on. Some boilers make it depend on the flow
    temperature (for example Vaillant); use the value for your usual flow temperature.

## Sensors

With this option on, SAT adds:

- **Xtreme fork: PWM Burn Time**: the burn time of the last block, with the planned on time.
- **Xtreme fork: Anti-cycling Remaining**: seconds until the boiler may start again.

## How to check it

On the [dashboard](dashboard.md), the burn time of each block should be close to its planned on time, and
burner starts per day should go down. The debug log shows lines such as `Xtreme profile: on phase completed
after … seconds of burn time`.
