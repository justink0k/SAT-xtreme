# Learned OPV

*Xtreme profile (fork) → Learning and calibration → Self-learning OPV (learned OPV).* Default *Off*.

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

SAT only learns from moments when the boiler burns for heating at its minimum modulation for at least 3
minutes, and no hot water was made in the last 5 minutes. Two kinds of samples are used:

- **Plateau**: the flow temperature stays stable (within 0.5 °C for 3 minutes) below the setpoint. The boiler
  cannot go lower, so this is a direct measurement of the balance. It moves the estimate up or down.
- **Self shut-off**: the boiler switches itself off at minimum modulation while the heating demand is still
  on and the flow is clearly (more than 0.5 °C) below the setpoint. The balance lies above this temperature,
  so it can only move the estimate up.

A shut-off at or above the setpoint does not count. In PWM the setpoint is the OPV itself, so such a shut-off
only shows the setpoint plus the hysteresis of the boiler; counting it would push the OPV up step by step to
the maximum.

Some boilers switch off a little **before** the setpoint. SAT therefore learns where your boiler normally
switches itself off: the median of the flow minus the setpoint at its last 20 heating shut-offs. From 5
shut-offs on, a shut-off only counts when the flow stayed more than 2 °C below that usual point.

### Minimum modulation per boiler

Boilers report their lowest modulation differently: some report 0 %, others 10 to 20 % at their minimum
power. SAT learns it per boiler:

- Every heating burn gives one value: the lowest modulation it reported after the first minute, counting only
  a value that two readings in a row reach (so one odd reading, for example 0 % when the flame goes out, does
  not count). Burns with hot water and burns shorter than a minute give no value.
- The start of a burn (often 85 to 100 % for minutes) needs no special handling: it is high, so it is never the
  lowest value of a burn. Every burn counts once, so a few long burns do not outweigh many short ones.
- The limit is the 10th percentile of the burns of the last 7 days plus 5 percentage points, at most 30 %, and
  never below the minimum modulation the boiler reports itself (OpenTherm message 15).
- Until there are 30 burns, the fixed limit of 2 % is used.

These rules are the same for every boiler; the limit they give is learned from your boiler. The modulation
data is stored and survives restarts.

!!! note "Tested on one boiler"
    These rules have only been tested on an Intergas Xtreme 30. If you use the learned OPV with another
    boiler, please share its `modulation_limit` and a few `last_burn_result` values on the
    [issue tracker](https://github.com/justink0k/SAT-xtreme/issues), so the rules can be checked for more boilers.

Each sample moves the estimate 10 % of the way to the measured value, at most 1 °C at a time, so one odd
sample cannot change much.

## Limits

- The value that is used is the estimate plus a margin of 1 °C, kept between the *Lowest learned OPV*
  (default 40 °C, 30 to 55 °C) and 55 °C, and never above the
  [maximum setpoint](settings-general.md#maximum-setpoint).
- When learning starts, the estimate is set so the value equals your configured OPV; nothing changes until
  samples arrive.
- A [slow calibration](calibration.md) sets the starting value for learning.
- The boiler must report its modulation. For brands where the official SAT does not use the reported
  modulation, turn on [ignore modulation limit](modulation-limit.md) if the boiler does report
  it.

The learned value is stored and survives restarts and updates.

## Choose the OPV from a model

*Learning and calibration → Choose the OPV from a model.* Default off.

In a well insulated house the boiler often gives more heat at its minimum power than the house takes in mild
weather. The flow then rises in every burn until the boiler switches itself off a little above the OPV, and there
is no plateau to learn from. The OPV then decides how long a burn lasts. The heat the house needs per day does not
depend on the OPV, so longer burns mean fewer starts, and a lower OPV means a lower flow.

### The model

- For every heating burn, SAT notes when the flow first reached every whole degree after the ignition. Burns with
  hot water and burns shorter than a minute are not used. The start peak of the boiler is simply part of it.
- The **heating curve** is, per degree, the median time over the burns of the last 7 days. A degree counts when at
  least 80 % of the burns that started below it reached it.
- Above the highest measured degree the curve is extended for at most 3 °C. When the rise slows down, the flow
  approaches a **balance temperature**: the temperature at which the boiler at minimum power and the house are in
  balance, the real OPV. It is shown as an estimate.
- The **predicted burn time** at an OPV is the time the curve needs to reach the OPV plus the point where your
  boiler normally switches itself off.
- After every burn the boiler ends itself, SAT compares the predicted burn time with the real one.

### The choice

SAT chooses the **lowest OPV at which a burn lasts at least the minimum burn time** of
[boiler timing](boiler-timing.md) (*Minimum burn time per PWM block*, 360 s by default), within the *Lowest learned
OPV*, 55 °C and the maximum setpoint. Gas use is not part of the choice: what a start costs is not known for every
boiler, and a low flow with burns of a sensible length is a choice that can be explained.

It only chooses when all of these hold:

- the model has at least 30 burns;
- at least 60 % of the heating burns end with the boiler switching itself off (otherwise the OPV does not decide
  the burn time);
- at least 50 % of the heating time is in PWM (otherwise the boiler mostly burns continuously, and the normal
  learning measures the OPV);
- the gateway reports the flow temperature, and the heating system is not a heat pump;
- the median error of the predictions over the last 24 hours is at most 20 %.

With *Learn and apply* it changes the OPV at most 1 °C per day. For 48 hours after a change it watches the comfort,
only in stable hours (target unchanged for at least 3 hours, heating on): when the room is on average more than
0.5 °C too cold, or the spread around the target grows by more than 50 % and at least 0.1 °C, it goes back and
blocks that value for 7 days. A plateau sample always wins: the learned value is used again. With *Learn only*
nothing changes: SAT shows its prediction and the OPV it would choose.

### Checking the model

The action [`sat_xtreme.try_opv_offset`](actions.md#sat_xtremetry_opv_offset) uses the OPV a few degrees lower or
higher for some hours, also with *Learn only*, and goes back by itself. SAT shows the predicted and the real burn
time of that test. When they agree, the model can be trusted. One day with the OPV 1 °C lower is a good test.

### Gas meter

You can choose a gas meter. Its use per degree hour over the last 7 days is shown as an attribute for your own
comparison; it is not used to choose. In a combi boiler it includes hot water.

!!! note "Tested on one house"
    The model has only been tested with an Intergas Xtreme 30. The status and the comparison of predicted and real
    burn times show whether it works for your boiler; reports are welcome on the
    [issue tracker](https://github.com/justink0k/SAT-xtreme/issues).

## Sensor

*Xtreme fork: Learned OPV* shows the value SAT would use, with these attributes: the mode, the estimate, the
margin, the source (configured, calibration, plateau or shut-off), the number of samples, and the last 20
samples with their time and type. Also:

- `minimum`: the *Lowest learned OPV*;
- `modulation_limit` and `modulation_burns`: the minimum modulation in use and how many burns it is based on;
- `shut_off_offset` and `shut_off_offset_samples`: where the boiler normally switches itself off, as flow minus
  setpoint (empty until there are 5 shut-offs), and how many shut-offs it is based on;
- `model_status` (`collecting`, `active`, `poor_fit`, or why it does not apply: `not_applicable_continuous`,
  `not_applicable_no_self_shut_off`, `not_applicable_no_flow_temperature`, `not_applicable_heat_pump`),
  `model_burns`, `model_error`, `model_choice` (the OPV it would choose), `model_value` (the OPV it uses),
  `predicted_burn_seconds` (at the OPV −1, 0 and +1 °C; `never` when the flow would not reach the shut-off point),
  `minimum_burn_seconds`, `balance_temperature`, `curve_top`, `self_shut_off_share`, `pwm_share`, `next_change`,
  `last_decision`, `test` and `last_test`, and `gas_per_degree_hour`;
- `last_burn_result`: what the last burn gave: `plateau` or `shut_off`, or why it gave no sample:
  `modulation_too_high`, `burn_too_short`, `hot_water`, `no_plateau` or `at_setpoint`.
