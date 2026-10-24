# System configuration

*Configure → System Configuration*

## Automatic duty cycle

Default on. SAT chooses the on and off times of each [PWM](overshoot-protection.md#pulse-width-modulation-pwm)
block itself, from the duty cycle and *Duty cycles per hour*. When off, every block has the fixed length of
[Maximum Duty Cycle](settings-general.md#maximum-duty-cycle-for-pulse-width-modulation).

## Synchronize climates with mode

Default on. When you turn SAT on or off, the [rooms](setup-wizard.md#4-areas) follow. The radiators in the main
room always follow.

## Duty cycles per hour

The maximum number of PWM blocks per hour, counted over the last 60 minutes. It also sets the length of a
block: 60 minutes divided by this number.

| Heating system | Choices | Default |
|---|---|---|
| Radiators | Normal (3 per hour), High (4 per hour) | 4 |
| Heat pump | Normal (2 per hour), High (3 per hour) | — |

Not shown for underfloor heating. Fewer blocks per hour means longer burns and fewer starts.

## Temperature sensor maximum value age

!!! info "Fork"
    With [Stale sensors](stale-sensors.md) on, SAT-xtreme replaces this check for the inside and outside sensor.

Default 6 hours. When the inside (or humidity) sensor has not reported for longer than this, SAT treats the
value as missing, and when the PID controller has not been updated for longer than this, SAT resets it. Set it
to 0 to turn this off.

## Minimum time for window to be open

Default 15 seconds. How long a [contact sensor](settings-general.md#contact-sensors) must be open before SAT
reacts.
