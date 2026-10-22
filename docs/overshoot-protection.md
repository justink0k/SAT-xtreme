# Overshoot protection and PWM

## The problem: a boiler cannot go low enough

Every boiler has a minimum power. A boiler with a minimum of 4 kW, burning at that minimum, heats the water to
a certain temperature and keeps it there only if the house takes 4 kW of heat. In mild weather the house
needs less. The water then gets warmer than the setpoint (the boiler *overshoots*), the boiler switches
itself off, waits its anti-cycling time, and starts again. Many short burns follow: each start costs gas
(a boiler starts at high power) and wears the burner.

## The overshoot protection value (OPV)

The **overshoot protection value** is the flow temperature at which your boiler, burning at its minimum
power, is in balance with your heating system: the highest temperature it can hold without switching itself
off. It depends on the boiler **and** on the house and radiators, so it is measured per installation; a
typical value lies between 40 and 55 °C.

When SAT wants a lower water temperature than the OPV, burning continuously is not possible. SAT then uses
**PWM** instead, with the OPV as the temperature of each burn.

You get the OPV in one of these ways:

- the 20-minute calibration in the [setup wizard](setup-wizard.md#5-calibrate-the-system);
- entering it by hand in the wizard;
- the slower [fork calibration](calibration.md), which also works for boilers that ignore the modulation
  limit;
- the [self-learning OPV](learned-opv.md) of the fork, which keeps learning during normal heating.

Overshoot protection is turned on by the setup wizard as soon as it stores an OPV (by calibrating or by
entering the value). It is not an option on the options pages; to change the OPV later, run *Reconfigure* on
the integration, or let the fork's [self-learning OPV](learned-opv.md) take over.

## Pulse width modulation (PWM)

With PWM, SAT heats in **blocks**: the boiler burns for a while at the OPV, then pauses. The share of the
time it burns is the *duty cycle*. SAT calculates it from how warm the water should be on average:

```text
duty cycle = (requested setpoint − base) / (flow temperature − base)
```

where the base is the start of the heating curve (27.2 °C for radiators, 20 °C for underfloor heating). If
SAT wants 34 °C and the boiler makes 44 °C, the duty cycle is about 40 %: burn 40 % of the time.

With **Automatic duty cycle** (the default), SAT turns the duty cycle into on and off times:

- The length of a block follows from *Duty cycles per hour*: with 4 per hour a block lasts 15 minutes, with
  3 per hour 20 minutes.
- Every burn lasts at least 3 minutes (with the fork's [Align PWM with the boiler](boiler-timing.md): the
  *minimum burn time*, 6 minutes by default). At a low duty cycle SAT makes the pause longer instead of the
  burn shorter, up to a block of twice the normal length.
- Below a very low duty cycle, SAT does not start the boiler at all until the demand rises.
- Above a high duty cycle, SAT burns continuously.

Without automatic duty cycle, the on and off times are the duty cycle times the
[maximum duty cycle](settings-general.md#maximum-duty-cycle-for-pulse-width-modulation) time.

SAT also never starts more blocks per hour than *Duty cycles per hour*, counted over the last 60 minutes.

### When PWM is used

- Always for a [switch](gateways.md#switch-or-relay) (it can only turn the heating on and off), and when
  *Force Pulse Width Modulation* is on (see [Advanced](settings-advanced.md)).
- With overshoot protection on: when the requested setpoint is below the OPV (or below the learned OPV when
  the fork's [self-learning OPV](learned-opv.md) is applied, or below the dynamic minimum setpoint when that
  is on).

The attribute `pulse_width_modulation_enabled` of the climate entity shows whether PWM is active. The action
[`sat.pulse_width_modulation`](actions.md#satpulse_width_modulation) can force it on or off temporarily.

## Maximum modulation

With an OpenTherm boiler, SAT can also limit the maximum modulation (`MM=` on an OpenTherm Gateway). During
PWM it may set it to 0 %, so the boiler burns at its minimum power. **Some boilers ignore this limit** (for
example the Intergas Xtreme): they keep modulating higher. The fork has an option for those boilers; see
[Boilers that ignore the modulation limit](modulation-limit.md).

## What the fork improves here

| Problem | Fork feature |
|---|---|
| With a thermostat on the bus, each block starts late because the new setpoint arrives late. | [Keep the setpoint ready](prime-setpoint.md) |
| The on time counts from the heating demand, not from the flame; pauses can be shorter than the anti-cycling time of the boiler. | [Align PWM with the boiler](boiler-timing.md) |
| The OPV is a fixed value. | [Self-learning OPV](learned-opv.md) |
| The calibration relies on `MM=0` and can report a meaningless value. | [Calibration](calibration.md) |
