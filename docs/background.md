# Background and results

## What it improves

- **Slow setpoint with a thermostat on the bus.** In gateway mode the OpenTherm Gateway only replaces
  the control setpoint inside the MsgID 1 messages of the thermostat on the bus; it does not send
  MsgID 1 by itself. A thermostat that sends MsgID 1 rarely (a Nest: about once every 150 seconds)
  delays every new setpoint by up to 150 seconds, while the heating demand arrives within seconds. In
  PWM mode, where upstream SAT lowers the setpoint to 10 °C in every off phase, each burn loses that
  time. SAT-xtreme keeps the setpoint ready during the off phase (step 1). With a thermostat that sends
  the setpoint often, or without a thermostat on the bus, the delay is small, but the fix does no harm.
- **Boilers that ignore the modulation limit.** Some boilers ignore `MM=` (the maximum relative
  modulation) but do report their modulation. SAT-xtreme can stop managing the limit and still use the
  reported modulation (step 2), and calibrate the overshoot protection value without relying on `MM=`
  (step 5).
- **Short PWM burns.** PWM can count real burn time, wait for the anti-cycling time of the boiler
  (also after short hot water flames) and use a longer minimum burn (step 3).
- **A fixed overshoot protection value.** SAT-xtreme can learn the OPV during normal operation (step 4).
- **A PID correction that is too strong or too weak.** Gain factor, a maximum rise above the heating
  curve and manual gains on their own options page.
- **Short hot water burns from the keep-warm function.** An optional switch turns keep-warm off and on
  again, for example with an automation at night, on boilers that let OpenTherm switch keep-warm (on
  Intergas: tap comfort on Eco and P074 = 0) (see [Hot water keep-warm at night](hot_water_keep_warm.md)).
- **Not seeing what the boiler does.** Boiler data sensors that work with any gateway, and the *SAT
  Xtreme* dashboard with one click (see [Dashboard](dashboard.md)).
- **Bug fixes** that apply to everyone (see [Troubleshooting](troubleshooting.md#bug-fixes-in-the-fork)).

The boiler settings that come with the fork (19.5 / 3.9 kW rated power, 300 s anti-cycling time) are
the values of the tested Intergas Xtreme 30. Before you turn on steps 2 or 3, enter the values from your
own rating plate and manual, or choose a matching boiler preset.

## Results on the tested setup

Measured on the tested setup (Intergas Xtreme 30, OpenTherm Gateway over MQTT, Nest on the bus) on the
first day with step 1 on, comparing PWM blocks of the same day:

| | Without step 1 (5 blocks) | With step 1 (5 blocks) |
|---|---|---|
| Time from heating demand to flame | 64 – 150 s | 3 – 5 s (one block 83 s: the boiler was anti-cycling after a hot water tap, which step 3 handles) |
| Burn time compared to the PWM block | 1 – 2.5 minutes shorter than the block | about equal to the block |

This is a first measurement of a few hours, in the evening (with longer blocks than on a mild
afternoon). Results for step 3 (burn time per block, starts per day) will be added once measured.

Hot water keep-warm off (`HW=0`, sent by hand on the same day, before the switch existed): hot water
still came out of the tap (a tap of more than a minute), and the gateway kept `HW=0` across four
restarts of Home Assistant. Whether keep-warm stopped is **not conclusive**: the boiler's tap comfort
was set to *On* at the time, and in that setting the Intergas ignores the DHW enable bit (see
[Hot water keep-warm at night](hot_water_keep_warm.md)). Fewer short hot water burns in the
following hours were most likely a coincidence.

