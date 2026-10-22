# PID settings (fork)

*Configure → PID settings (fork)*

SAT calculates the water temperature as the [heating curve plus a PID correction](how-sat-works.md#pid-correction).
This page decides how strong that correction is. It exists only in SAT-xtreme. With the defaults (automatic
gains on, gain factor 1.0, maximum rise 0) nothing changes compared to the official SAT.

## Automatic gains

Default on. SAT calculates kP, kI and kD from the heating curve, so they follow the weather.

Turn it off to enter the gains yourself. After saving, a second page *Manual gains (fork)* opens, **prefilled
with the gains SAT uses at that moment**, so saving them unchanged does not change the control. Then adjust:

- **kP**: °C of extra water temperature per °C that the room is too cold.
- **kI**: how fast SAT removes a small difference that remains. Only used when the room is within 0.1 °C of
  the target.
- **kD**: how strongly SAT reacts to how fast the room temperature changes; it brakes when the room warms up
  quickly.

!!! note "Fixed in the fork"
    In the official SAT 4.2.1 the choice of automatic or manual gains in the setup wizard was ignored,
    because it was stored where SAT does not read it. The fork stores it in the options as well.

## Gain factor

Default 1.0, range 0.3 to 1.5. A factor on the automatic gains:

- **below 1.0**: a calmer correction. For example 0.5: a room that is 1 °C too cold makes the water about
  half as hot extra as before. Useful when the room overshoots the target or the setpoint jumps up and down.
- **above 1.0**: a stronger correction, for a house that reacts slowly.

Not used with manual gains. The sensor *Xtreme fork: PID Output* shows the gains in use.

## Maximum rise above the heating curve

Default 0 (no limit), range 0 to 40 °C. The water never gets more than this warmer than the heating curve,
however cold the room is. This keeps the setpoint calm after a cold night or an open window.

!!! warning
    A limit also slows down warming up, for example in the morning after a lower night temperature. Start
    with a generous value (for example 10 °C) and lower it only when needed.

The [maximum setpoint](settings-general.md#maximum-setpoint) still applies on top of this.
