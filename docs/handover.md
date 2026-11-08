# Hand over to the thermostat

*Xtreme profile (fork) → Thermostat on the bus → Hand over to the thermostat when SAT is turned off.*
Default off. OpenTherm Gateway over MQTT only.

## What it does

When you turn the SAT climate entity **off**, SAT sends `CS=0` to the OpenTherm Gateway. The gateway then
stops overriding the control setpoint, and the thermostat on the bus controls the boiler again **right
away**. With *Push setpoint to thermostat* on, SAT also sends `TC=0`, so the thermostat follows its own
program again; that override has no expiry on the gateway. SAT also sends `MM=T`, which clears its maximum
modulation, so the thermostat can use the full power of the boiler again.

SAT also hands over:

- when **Home Assistant stops or restarts** cleanly (also for an update);
- when SAT is **unloaded or reloaded**, for example after changing an option; a reload takes the boiler back
  within a minute;
- when SAT **starts turned off**, so the thermostat keeps the boiler.

When SAT starts in *Heat*, it pushes the target temperature to the thermostat again (with *Push setpoint to
thermostat*).

Without this option, the gateway keeps SAT's last setpoint until its override expires, after about a minute. SAT
clears its maximum modulation in both cases, because that override has no expiry.

## What stays the same

- When Home Assistant crashes or loses power, nothing can send `CS=0`; the gateway still drops the control setpoint
  by itself after about a minute, and the thermostat takes over. A maximum modulation and a pushed thermostat setpoint
  do stay then; see [what stays behind after a crash](troubleshooting.md#what-stays-behind-after-a-crash).
- Hot water is not affected.

## When to use it

When you switch between SAT and your own thermostat by hand or with an automation, for example "thermostat
in the summer, SAT in the winter", or as a quick way back when you test something.
