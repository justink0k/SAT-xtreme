# Maximum setpoint entity

*Xtreme profile (fork) → Boiler → Maximum setpoint as an entity.* Default off.

## What it does

It adds the number entity *Xtreme fork: Maximum Setpoint*, so you can change the
[maximum setpoint](settings-general.md) from a dashboard or an automation, for example a lower maximum in
spring.

- A change is stored as the option *Maximum Setpoint* (*Configure → General*), so the entity and the option
  always show the same value, also after a restart.
- SAT uses the new value **right away**, without reloading, and sends it to the gateway (`SH=` on the
  OpenTherm Gateway). Every setpoint SAT sends is limited to it.
- The entity is only added for gateways that can send a setpoint.

## Limits

| Limit | Value |
|---|---|
| Lowest | The OPV that SAT uses (the learned OPV when it is applied, otherwise the configured one), and at least 30 °C. Below the OPV, SAT could not run the boiler at its minimum without overshooting. |
| Highest | 75 °C for radiators, 50 °C for underfloor heating, 55 °C for a heat pump (55 °C when the heating system is unknown). |
| Boiler | Never above the upper bound the boiler reports (OpenTherm message 49), when the gateway reports it. |

The attributes `opv`, `ceiling` and `boiler_bound` show the values in use. A higher maximum that you set
on the *General* page stays as it is; with the entity you can only lower it.

## During the calibration

While the [slow calibration](calibration.md) runs, the maximum setpoint cannot be changed: the calibration
starts at the lower of 55 °C and the maximum setpoint, and a change in between would spoil the measurement.

## What reads it later

The [learned OPV](learned-opv.md) takes the maximum setpoint as its upper limit when SAT starts. After a
change with the entity, it uses the new value from the next reload or restart. Until then, the setpoint SAT
sends is still limited to the new maximum.

## Turn it on

1. *Settings → Devices & services → SAT-xtreme → Configure → Xtreme profile (fork)*.
2. Under *Boiler*, turn on *Maximum setpoint as an entity* and save. SAT reloads.
3. Change *Xtreme fork: Maximum Setpoint* and check that *Configure → General → Maximum Setpoint* shows the
   same value.
