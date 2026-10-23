# First steps

After the [setup wizard](setup-wizard.md), SAT-xtreme behaves like the official SAT. This page gives a safe
order to tune SAT and turn on the fork features. Change **one thing at a time** and watch the effect for a
few days; heating reacts slowly, and the weather changes in between.

## 1. Let SAT run

Set the climate entity to *Heat* and let SAT run for a day or two with the defaults. Create the
[dashboard](dashboard.md) so you can see what happens: the setpoint, the flow temperature, the flame and the
PID correction.

## 2. Tune the heating curve

Look at the sensor *Xtreme fork: PID Output* (or the climate attributes). If the PID correction stays
clearly positive for hours, the heating curve is too low: raise the
[heating curve coefficient](settings-general.md#heating-curve-coefficient) a little (for example by 0.2). If
it stays clearly negative, lower it. A good curve keeps the correction small.

## 3. Check the maximum setpoint

The [maximum setpoint](settings-general.md#maximum-setpoint) is a hard limit that SAT and the fork never
exceed, also not during a calibration. Set it to what your radiators need on the coldest day, not higher.

## 4. Turn on fork features

All fork features are on the page *Configure → Xtreme profile (fork)* and *Configure → PID settings
(fork)*. A sensible order:

| Order | Feature | When |
|---|---|---|
| 1 | [Boiler preset](boiler_presets.md) or your own boiler values | Always first: the features below use them. Take the values from the rating plate and the manual. |
| 2 | [Setpoint priming](prime-setpoint.md) | You have an OpenTherm Gateway with a thermostat on the bus. |
| 3 | [Ignore modulation limit](modulation-limit.md) | Your boiler keeps modulating when SAT sends `MM=0` (the calibration can test this). |
| 4 | [Boiler timing](boiler-timing.md) | You see short burns or burns that start late; fill in the anti-cycling time first. |
| 5 | [Learned OPV](learned-opv.md), *Learn only* | To see whether your OPV is right. Switch to *Learn and apply* once the learned value looks plausible. |
| 6 | [Slow calibration](calibration.md) | When you do not trust the OPV, or the wizard calibration failed. |
| 7 | [PID settings](settings-pid.md) | When the correction is too strong (the room overshoots) or too weak. |
| any | [Hand over to the thermostat](handover.md), [hot water keep-warm](hot_water_keep_warm.md) | Whenever you want them. |

After saving an options page, SAT reloads, and the [dashboard](dashboard.md) adds the cards of the features
you turned on.

## 5. Watch the effect

Useful things to compare before and after a change (all on the dashboard):

- **Time from heating demand to flame**: should be seconds, not minutes.
- **Burn time per PWM block** (*Xtreme fork: PWM Burn Time*): should match the planned on time.
- **Burner starts per day** (*Xtreme fork: Burner Starts*): fewer is better.
- **Room temperature**: close to the target, without large swings.

To see the decisions of the fork in detail, turn on [debug logging](troubleshooting.md#debug-logging).
