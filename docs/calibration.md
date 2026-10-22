# Calibration

*Xtreme profile (fork) → Learning and calibration → Calibration buttons.* Default off.

A careful calibration of the [overshoot protection value](overshoot-protection.md#the-overshoot-protection-value-opv)
that, unlike the 20-minute calibration of the setup wizard, also works for boilers that
[ignore the modulation limit](modulation-limit.md). It takes hours instead of minutes, so you start it when it
suits you, with a button.

## Before you start

- Open all radiator valves (thermostatic valves fully open), as for any OPV calibration.
- Choose a moment when the house may get a little warmer and nobody needs much hot water; the calibration
  pauses for hot water but takes longer then.
- Set the SAT climate entity to *Heat*.
- Calibrating while you are away is a good idea; the calibration never heats the room more than 1 °C above
  the target.

## Start and stop

With the option on, SAT adds:

- the buttons **Xtreme fork: Start Calibration** and **Xtreme fork: Stop Calibration**,
- the sensor **Xtreme fork: Calibration** with the phase, the progress and the report,
- the actions [`sat.start_xtreme_calibration`](actions.md#satstart_xtreme_calibration) and
  [`sat.stop_xtreme_calibration`](actions.md#satstop_xtreme_calibration).

The calibration stops cleanly with the stop button, when you turn SAT off, and on a restart of Home
Assistant, and SAT returns to normal operation right away. While it runs, SAT's normal control is paused.

## How it works

1. **Modulation test** (about 10 minutes): SAT sets the maximum modulation to 0 % and watches the modulation
   the boiler reports.
   - The boiler follows the limit (5 % or less): each round measures at minimum power, about 2 hours in
     total.
   - The boiler ignores the limit (20 % or more): each round lowers the setpoint step by step instead,
     usually 5 to 6 hours in total. SAT also creates a [repair](repairs.md#the-boiler-ignores-the-modulation-limit)
     that offers to turn on *The boiler ignores the modulation limit*.
   - In between, or when the boiler does not report its modulation, SAT uses the step-by-step method.
   The maximum modulation is always set back to 100 % afterwards.
2. **Rounds**: each round starts at 55 °C (never above the maximum setpoint).
   - When the boiler follows the limit, it burns at minimum power, and the stable flow temperature is the
     result of the round.
   - Otherwise SAT lowers the setpoint step by step: 2 °C while the boiler modulates above 20 %, 1 °C below
     that, each time waiting until the flow temperature is stable for 5 minutes. A step that takes longer
     than 30 minutes moves on, and a round fails when the boiler still modulates at 35 °C.

   A round ends when the boiler burns at minimum modulation with a stable flow below the setpoint (a
   plateau), or switches itself off at minimum modulation.
3. **Pauses**: SAT pauses while hot water is made, and while the room is more than 1 °C above the target.
   Between rounds the boiler cools down for 20 minutes.
4. **Result**: SAT aims for 5 rounds (at most 8) and uses the **median**. The result is rejected when fewer
   than 3 rounds are valid, when it is below 35 °C, or when the rounds differ by more than 6 °C.

The whole calibration stops after at most 10 hours.

## The result

The result becomes the starting value of the [self-learning OPV](learned-opv.md). The sensor shows a report
with the value of every round. If the self-learning OPV is *Off*, the result is stored and shown, and used as
soon as you turn learning on.

!!! danger "Never above the maximum setpoint"
    The calibration never sends a setpoint above the configured [maximum setpoint](settings-general.md#maximum-setpoint).
    The calibration of the official SAT 4.2.1 could send 62 °C when the boiler reported a higher maximum.

## Phases

The sensor shows one of these phases: `idle`, `waiting`, `testing_modulation`, `heating`,
`paused_hot_water`, `paused_comfort`, `cooldown`, `succeeded`, `failed`, `cancelled`.
