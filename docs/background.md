# Background and results

## The goal: heating that is calmer, more comfortable, more efficient and reliable

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
  - Tested and reversible: every feature and fix has automated tests, and every feature can be turned on
    and off on its own.

## SAT-xtreme compared to SAT 4.2.1

| | SAT 4.2.1 | SAT-xtreme | Option |
|---|---|---|---|
| Setpoint in the PWM off phase | Drops to 10 °C. With a thermostat on the bus, the next setpoint reaches the boiler only with the next MsgID 1 of the thermostat (up to 150 s with a Nest). | Stays at the minimum setpoint with the heating demand off, so the boiler starts within seconds. | setpoint priming |
| Heating demand commands | Decided on the status bit of the boiler, which lags and may stay off while the boiler is anti-cycling, so `CH=0` can be skipped. | Decided on the last command, not repeated within 30 s, and resent when the boiler does not confirm it. | setpoint priming |
| Boilers that ignore the modulation limit | Keeps sending `MM=0` / `MM=100`. | Stops managing the limit (one neutral `MM=100`), keeps using the reported modulation. | ignore modulation limit |
| Power sensor | Only when the modulation limit is managed, and only when the boiler reports its capacity. | Also without a managed limit, with the rated power as fallback. | ignore modulation limit |
| PWM timing | The on time is wall-clock time from the heating demand; minimum on time 3 min; off phases can be shorter than the anti-cycling time of the boiler. | The on time counts burn time; a new block waits for the anti-cycling time after any flame, also short hot water flames; minimum burn and anti-cycling time are configurable. | boiler timing |
| Overshoot protection value (OPV) | A fixed value. | Learned during normal operation, shown in a sensor, used only when you choose so. | learned OPV |
| Calibration | Relies on `MM=0`, runs about 20 minutes in the setup wizard, can report a meaningless value (for example 32 °C) as successful, and could send a setpoint above the configured maximum. | First tests whether the boiler follows `MM=0`: if so, measures at minimum power (about 2 hours); if not, lowers the setpoint step by step (5 to 6 hours) and offers a one-click repair to turn on *ignore the modulation limit*. Median of 5 rounds, rejects unrealistic results, pauses for hot water and a too warm room, start/stop buttons and a report; never above the maximum setpoint. | slow calibration (maximum: always) |
| PID strength | Only adjustable through the heating curve coefficient, which also moves the whole heating curve. The *Automatic gains* choice of the setup wizard was ignored. | Gain factor, maximum rise above the heating curve, and manual gains on their own page; the wizard choice is used. | PID settings (wizard: always) |
| Hot water keep-warm | – (left to the boiler and the thermostat on the bus). | A switch to turn the keep-warm function off (`HW=0`) and back to normal (`HW=A`), by hand or with an automation. | keep-warm switch |
| Insight | – | Sensors for the boiler data (flow, setpoint, modulation, burner starts, flame, hot water, heating demand), the PID correction, PWM burn time, remaining anti-cycling time, learned OPV and calibration status. | boiler data and PID: always; the rest with the matching switches |
| Dashboard | – | The *SAT Xtreme* dashboard, created with one click from the entities that exist, with any gateway. | with one click |
| Turning SAT off | The thermostat on the bus takes over after the gateway heartbeat expires (about a minute). | Optionally right away (`CS=0`). | handover |
| Boiler presets | – | A preset list and a template to add your boiler. | preset |
| Home Assistant 2026.12 | Uses an update listener that will stop working. | Prepared: uses `OptionsFlowWithReload`. | always |
| Start-up | Sensors, binary sensors and buttons could be skipped (or fail with `KeyError: 'climate'`) when the climate was not ready yet. | The climate is set up first. | always |
| Recognisable in Home Assistant | – | Options pages end in "(fork)", entities start with "Xtreme fork:". | always |

## What it improves

- **Slow setpoint with a thermostat on the bus.** In gateway mode the OpenTherm Gateway only replaces
  the control setpoint inside the MsgID 1 messages of the thermostat on the bus; it does not send
  MsgID 1 by itself. A thermostat that sends MsgID 1 rarely (a Nest: about once every 150 seconds)
  delays every new setpoint by up to 150 seconds, while the heating demand arrives within seconds. In
  PWM mode, where upstream SAT lowers the setpoint to 10 °C in every off phase, each burn loses that
  time. SAT-xtreme keeps the setpoint ready during the off phase ([setpoint priming](prime-setpoint.md)). With a thermostat that sends
  the setpoint often, or without a thermostat on the bus, the delay is small, but the fix does no harm.
- **Boilers that ignore the modulation limit.** Some boilers ignore `MM=` (the maximum relative
  modulation) but do report their modulation. SAT-xtreme can stop managing the limit and still use the
  reported modulation ([ignore modulation limit](modulation-limit.md)), and calibrate the overshoot protection value without relying on `MM=`
  ([slow calibration](calibration.md)).
- **Short PWM burns.** PWM can count real burn time, wait for the anti-cycling time of the boiler
  (also after short hot water flames) and use a longer minimum burn ([boiler timing](boiler-timing.md)).
- **A fixed overshoot protection value.** SAT-xtreme can learn the OPV during normal operation ([learned OPV](learned-opv.md)).
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
first day with setpoint priming on, comparing PWM blocks of the same day:

| | Without setpoint priming (5 blocks) | With setpoint priming (5 blocks) |
|---|---|---|
| Time from heating demand to flame | 64 – 150 s | 3 – 5 s (one block 83 s: the boiler was anti-cycling after a hot water tap, which boiler timing handles) |
| Burn time compared to the PWM block | 1 – 2.5 minutes shorter than the block | about equal to the block |

This is a first measurement of a few hours, in the evening (with longer blocks than on a mild
afternoon). Results for boiler timing (burn time per block, starts per day) will be added once measured.

Hot water keep-warm off (`HW=0`, sent by hand on the same day, before the switch existed): hot water
still came out of the tap (a tap of more than a minute), and the gateway kept `HW=0` across four
restarts of Home Assistant. Whether keep-warm stopped is **not conclusive**: the boiler's tap comfort
was set to *On* at the time, and in that setting the Intergas ignores the DHW enable bit (see
[Hot water keep-warm at night](hot_water_keep_warm.md)). Fewer short hot water burns in the
following hours were most likely a coincidence.

