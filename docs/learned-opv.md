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

## Search for the best OPV

*Learning and calibration → Search for the best OPV.* Default off.

In a well insulated house the boiler often gives more heat at its minimum power than the house takes in mild
weather. The flow then rises in every burn until the boiler switches off, and there is no plateau to learn
from. The OPV is then a choice: a lower OPV gives shorter burns at a lower flow, a higher OPV longer burns and
fewer starts. The search tries both and keeps what works best.

### How it decides

- **Score:** heating starts per degree hour (an hour with 1 °C between the target and the outside
  temperature). Lower is better. Only heating starts count, not hot water.
- **Comfort,** only measured in stable hours: the target has been unchanged for at least 3 hours and the
  thermostat is heating, so a night setback does not count. A step fails when the room is on average more
  than 0.5 °C below the target, or when the spread of the room temperature around the target grows by more
  than 50 % and by at least 0.1 °C.
- **A period** lasts 48 hours and counts only with at least 20 starts and 12 stable hours; otherwise it is
  extended, up to 7 days. A period that is still incomplete after 7 days is discarded and started again;
  `search_blocked` says why (`too_few_starts` or `too_few_stable_hours`).
- **The outside temperature is required.** A gap of up to an hour is bridged with the last known value. When
  more than 10 % of the heating time of a period has no outside temperature, the period is discarded and
  `search_blocked` is `no_outside_temperature`; the search goes on once the outside temperature is back.

!!! warning "Experimental"
    Measured on one house, the starts per degree hour varied about 50 % from day to day at the same OPV,
    mostly through the weather: on cold days the boiler burns longer and starts less often. A step of 1 °C is
    then hard to judge within 48 hours. Use the search with *Learn only* to follow it; a revised version with
    alternating periods and a measure per burn is being worked on.

### The steps

1. After 3 days without a plateau sample, SAT measures a baseline of 48 hours at the current OPV.
2. It tries 1 °C lower. When the score is not more than 15 % worse and the comfort stays good, it keeps the
   lower value (a lower flow is a bonus) and tries another step down.
3. Otherwise it goes back and tries 1 °C higher. That step is only kept when the score is at least 15 %
   better and the comfort stays good.
4. When no step helps, it keeps the best value and rests for 7 days before it searches again.

When the room gets too cold during a trial, SAT goes back right away. The search stays between the *Lowest
learned OPV*, 55 °C and the maximum setpoint. A plateau sample always wins: it ends the search, which starts
again after 3 days without a plateau. The state of the search survives restarts.

With *Learn only*, the setpoint does not change: SAT only measures the baseline and shows the step it would
take. With *Learn and apply*, the step is added to the learned value.

### Gas meter

You can choose a gas meter. Its use per degree hour in the current period is shown as an attribute for your
own comparison, but it is not used to decide: in a combi boiler it includes hot water, which changes more
from day to day than a step of 1 °C.

## Sensor

*Xtreme fork: Learned OPV* shows the value SAT would use, with these attributes: the mode, the estimate, the
margin, the source (configured, calibration, plateau or shut-off), the number of samples, and the last 20
samples with their time and type. Also:

- `minimum`: the *Lowest learned OPV*;
- `modulation_limit` and `modulation_burns`: the minimum modulation in use and how many burns it is based on;
- `shut_off_offset` and `shut_off_offset_samples`: where the boiler normally switches itself off, as flow minus
  setpoint (empty until there are 5 shut-offs), and how many shut-offs it is based on;
- `search_phase` (`waiting`, `baseline`, `down`, `up` or `rest`), `search_blocked` (why no decision comes), `search_value` (the OPV the search uses, or
  would try with *Learn only*), `search_offset`, `baseline_score` and `trial_score`, `baseline_spread` and
  `trial_spread`, `baseline_mean_error` and `trial_mean_error`, `stable_hours` and `starts` of the current
  period, `next_decision` (a date and time), `last_decision` and `search_gas_per_degree_hour`;
- `last_burn_result`: what the last burn gave: `plateau` or `shut_off`, or why it gave no sample:
  `modulation_too_high`, `burn_too_short`, `hot_water`, `no_plateau` or `at_setpoint`.
