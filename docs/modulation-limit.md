# Boilers that ignore the modulation limit

*Xtreme profile (fork) → Boiler → The boiler ignores the modulation limit.* Default off.

## The problem

With OpenTherm, SAT can set the maximum relative modulation of the boiler (`MM=` on an OpenTherm Gateway),
for example to 0 % during [PWM](overshoot-protection.md#pulse-width-modulation-pwm) so the boiler burns at
minimum power. Some boilers ignore that limit but do report their modulation, for example the Intergas
Xtreme. SAT then keeps sending a limit that has no effect, and the calibration of the official SAT can give a
meaningless result. For some brands (Ideal, Intergas, Geminox and Nefit) the official SAT does not use the
reported modulation at all.

## How to recognise it

- On an OpenTherm Gateway, message 14 (the maximum modulation) is answered with *Data-Invalid* in the log of
  the gateway.
- With `MM=0` the boiler keeps modulating well above 0 %.
- The fork's [calibration](calibration.md) tests this in its first 10 minutes. When the boiler ignores the
  limit, it offers a [repair](repairs.md#the-boiler-ignores-the-modulation-limit) that turns this option on
  with one click.

## What the option does

- SAT stops managing the modulation limit. It sends one neutral limit (`MM=100`) so no old limit stays active
  on the gateway, and then leaves it alone.
- SAT uses the modulation the boiler reports, also for the brands above.
- The *Current Power* sensor stays available. When the boiler does not report its capacity or its minimum
  modulation, SAT uses the maximum and minimum heating output from the
  [Xtreme profile](settings-xtreme-profile.md#boiler) instead.

Fill in the heating outputs of your boiler (or choose a [preset](boiler_presets.md)) before you turn this on.
