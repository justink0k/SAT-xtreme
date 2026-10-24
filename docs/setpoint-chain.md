# Setpoint chain

*Xtreme profile (fork) → Diagnostics → Show the setpoint chain.* Default off. Read only: it changes nothing
in the control.

## What it shows

The sensor *Xtreme fork: Setpoint Chain* follows the setpoint from SAT to the boiler, so you can see where a
difference comes from. This helps most with a thermostat on the bus (such as a Nest), which can delay the
setpoint that the gateway passes on.

| Where | What | Meaning |
|---|---|---|
| Value of the sensor | Calculated setpoint | The heating curve plus the PID correction (the *requested setpoint* of SAT). |
| `filtered_setpoint` | Filtered setpoint | The calculated setpoint after SAT's low-pass filter; PWM works with this value. |
| `sent_setpoint` | Sent setpoint | The control setpoint SAT sent to the gateway last, after PWM, [setpoint priming](prime-setpoint.md) and the maximum setpoint. |
| `sent_at` | Time | When SAT sent it. |
| `heating_demand_sent` | `on` or `off` | The heating demand SAT sent last. With setpoint priming, the setpoint stays ready while the demand is off. |
| `received_setpoint` | Received setpoint | The control setpoint of the boiler as the gateway reports it. For the OpenTherm Gateway this is `TSet`. |
| `difference` | Received minus sent | Zero when the boiler has the setpoint SAT sent. |
| `pwm_status` | `on`, `off` or `idle` | The phase of PWM; `idle` when PWM is not used. |

## How to read it

- **Calculated and sent differ:** PWM, setpoint priming, the minimum setpoint or the maximum setpoint changed
  the value. That is normal; in a PWM pause without setpoint priming SAT sends 10 °C.
- **Sent and received differ for a while:** the boiler does not have SAT's setpoint yet. With an OpenTherm
  Gateway in gateway mode, the gateway can only pass the setpoint on in the messages of the thermostat on the
  bus; a Nest sends those about every 150 seconds.
- **Sent and received keep differing:** check that the gateway overrides the control setpoint (for the
  OpenTherm Gateway: `CS=` in its log) and that no other system sends a setpoint.

The received setpoint is the value the gateway reports. Which message that value comes from (the request of
the thermostat or the one the gateway passes on to the boiler) depends on the gateway and its firmware.

## Turn it on

1. *Settings → Devices & services → SAT-xtreme → Configure → Xtreme profile (fork)*.
2. Under *Diagnostics*, turn on *Show the setpoint chain* and save. SAT reloads.
3. Open the sensor *Xtreme fork: Setpoint Chain* and look at its attributes, or add them to a dashboard.

Turn the option off again to remove the sensor.
