# Keep the setpoint ready

*Xtreme profile (fork) → Thermostat on the bus → Keep the setpoint ready between PWM blocks.* Default off.

## The problem

During [PWM](overshoot-protection.md#pulse-width-modulation-pwm), the official SAT lowers the control setpoint
to 10 °C in every pause and raises it again for the next block. With an
[OpenTherm Gateway in gateway mode](gateways.md#gateway-mode-and-a-thermostat-on-the-bus), the gateway can
only put the new setpoint in the messages of the thermostat on the bus. A Nest sends those about every 150
seconds, so the boiler gets the higher setpoint up to 2.5 minutes late, while the heating demand arrives
within seconds. Every block loses burn time, and the boiler may not start at all in a short block.

## What the option does

- In a PWM pause, the setpoint **stays** at the overshoot protection value (or the minimum setpoint SAT uses)
  instead of dropping to 10 °C.
- The heating demand is turned **off** explicitly in the pause (`CH=0` on an OpenTherm Gateway), so the
  boiler does not burn although the setpoint is ready.
- SAT decides whether to send the heating demand from its **last command**, not from the status bit of the
  boiler, which lags behind and may stay off while the boiler is anti-cycling. It does not resend the same
  command within 30 seconds, and resends it when the boiler does not confirm it.

The result: when the next block starts, only the heating demand has to change, and the boiler starts within
seconds.

## When to use it

- You have an OpenTherm Gateway with a thermostat on the bus that sends the setpoint rarely. This is where it
  helps most.
- Without a thermostat on the bus, or with one that sends often, the gain is small, but it does no harm.

## Result on the tested setup

On the first day with this option on (Intergas Xtreme 30, Nest on the bus): the time from heating demand to
flame went from 64 – 150 seconds to 3 – 5 seconds, and the burn time matched the planned block instead of
being 1 – 2.5 minutes shorter. See [Background and results](background.md#results-on-the-tested-setup).

## How to check it

On the [dashboard](dashboard.md), compare *Heating Demand* and *Flame*: the flame should follow the demand
within seconds (unless the boiler is anti-cycling; see [Align PWM with the boiler](boiler-timing.md)). The
debug log shows lines starting with `Xtreme profile: PWM off phase`.
