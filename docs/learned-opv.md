# Self-learning OPV

*Xtreme profile (fork) → Learning and calibration → Self-learning OPV.* Default *Off*.

The [overshoot protection value](overshoot-protection.md#the-overshoot-protection-value-opv) (OPV) decides when
SAT switches to PWM and how warm each PWM block burns. In the official SAT it is a fixed value from the setup
wizard. The fork can learn it during normal heating.

## Modes

| Mode | What happens |
|---|---|
| Off | Nothing is learned. SAT uses the OPV from the wizard. |
| Learn only | SAT learns and shows the value in the sensor *Xtreme fork: Learned OPV*, but keeps using your own OPV. |
| Learn and apply | SAT uses the learned value (plus a safety margin) to decide on PWM and as the setpoint of each block. |

Start with **Learn only**. When the learned value looks plausible after some days of heating, switch to
**Learn and apply**.

## How it learns

SAT only learns from moments when the boiler burns for heating at its minimum modulation (2 % or less) for at
least 3 minutes, and no hot water was made in the last 5 minutes. Two kinds of samples are used:

- **Plateau**: the flow temperature stays stable (within 0.5 °C for 3 minutes) below the setpoint. The boiler
  cannot go lower, so this is a direct measurement of the balance. It moves the estimate up or down.
- **Self shut-off**: the boiler switches itself off at minimum modulation while the heating demand is still
  on. The balance lies above this temperature, so it can only move the estimate up.

Each sample moves the estimate 10 % of the way to the measured value, at most 1 °C at a time, so one odd
sample cannot change much.

## Limits

- The value that is used is the estimate plus a margin of 1 °C, kept between 40 and 55 °C, and never above
  the [maximum setpoint](settings-general.md#maximum-setpoint).
- When learning starts, the estimate is set so the value equals your configured OPV; nothing changes until
  samples arrive.
- A [calibration](calibration.md) sets the starting value for learning.
- The boiler must report its modulation. For brands where the official SAT does not use the reported
  modulation, turn on [The boiler ignores the modulation limit](modulation-limit.md) if the boiler does report
  it.

The learned value is stored and survives restarts and updates.

## Sensor

*Xtreme fork: Learned OPV* shows the value SAT would use, with these attributes: the mode, the estimate, the
margin, the source (configured, calibration, plateau or shut-off), the number of samples, and the last 20
samples with their time and type.
