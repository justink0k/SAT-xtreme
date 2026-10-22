# Hand over to the thermostat

*Xtreme profile (fork) → Thermostat on the bus → Hand over to the thermostat when SAT is turned off.*
Default off. OpenTherm Gateway over MQTT only.

## What it does

When you turn the SAT climate entity **off**, SAT sends `CS=0` to the OpenTherm Gateway. The gateway then
stops overriding the control setpoint, and the thermostat on the bus controls the boiler again **right
away**.

Without this option, the gateway keeps SAT's last setpoint until its override expires, after about a minute.

## What stays the same

- When Home Assistant stops or crashes, nothing can send `CS=0`; the gateway still drops the override by
  itself after about a minute, and the thermostat takes over. This failover always works.
- Hot water is not affected.

## When to use it

When you switch between SAT and your own thermostat by hand or with an automation, for example "thermostat
in the summer, SAT in the winter", or as a quick way back when you test something.
