# Burner cycles

*Xtreme profile (fork) → Diagnostics → Track burner cycles.* Default off. Read only: it changes nothing in
the control.

## What it does

SAT-xtreme recognises every burner cycle, from flame on to flame off, and records what happened in it. Short
cycles of a few seconds are recorded too: those are often the ones you want to see.

Start and end follow the updates of the gateway, which SAT handles in batches of about 5 seconds, so times are
accurate to about 5 seconds. A cycle that is running while Home Assistant restarts is not recorded.

## What is recorded per cycle

| Field | Meaning |
|---|---|
| `start`, `end`, `duration` | Start and end time, and the burn time in seconds. |
| `flow_start`, `flow_min`, `flow_max`, `flow_average` | Flow temperature at the start, lowest, highest and average (weighted by time). |
| `return_start`, `return_end` | Return temperature at the start and the end. |
| `setpoint_start`, `setpoint_end` | Control setpoint of the boiler as the gateway reports it, at the start and the end. |
| `kind` | `heating`, `hot_water` (hot water during the whole cycle) or `mixed`. |
| `end_reason` | Why the cycle ended, see below. |
| `during_anti_cycling` | The cycle started within the anti-cycling time after the previous flame. Empty for the first cycle after a restart. |

The anti-cycling time is the value on the *Boiler* section of the Xtreme profile; it is only read here, so
*Align PWM with the boiler (boiler timing)* does not have to be on.

### End reasons

Checked in this order:

1. `hot_water`: hot water was active at the end, or it was a hot water cycle.
2. `pwm_block_ended`: SAT turned the heating demand off because the PWM block ended.
3. `no_heating_demand`: SAT turned the heating demand off outside a PWM pause, for example because the
   thermostat was turned off or the PID controller asked for no more heat.
4. `setpoint_reached`: the heating demand was still on and the flow temperature was at most 2 °C below the
   setpoint, or above it. The boiler stopped by itself.
5. `unknown`: none of the above.

## Entities and events

All names start with **Xtreme fork:**.

| Entity | Shows |
|---|---|
| *Last Cycle* | The burn time of the last cycle in seconds; all fields above are attributes. |
| *Cycles Last Hour*, *Cycles Last 24h* | The number of cycles that ended in the last hour or 24 hours; the attributes split them into `heating`, `hot_water` and `mixed`. |
| *Average Burn Time Last Hour*, *Average Burn Time Last 24h* | The average burn time of those cycles in seconds. |

The counters count all cycles, heating and hot water.

Two events are fired, with the `entry_id` and `name` of SAT:

- `sat_xtreme_cycle_started`: the start time, flow and return temperature, setpoint, `during_anti_cycling`
  and `hot_water`.
- `sat_xtreme_cycle_ended`: all fields of the cycle.

You can use them in automations, or follow them under *Developer tools → Events*.

## History

The last 500 cycles are kept, also across restarts, in `.storage/sat_xtreme_cycles_<entry_id>`. That is
enough for the 24 hour counters even when the boiler starts 20 times per hour; with normal use it is about a
week. The history is saved 30 seconds after a cycle ends and when SAT stops. Turn the option off to stop
recording; the file stays.

## Turn it on

1. *Settings → Devices & services → SAT-xtreme → Configure → Xtreme profile (fork)*.
2. Under *Diagnostics*, turn on *Track burner cycles* and save. SAT reloads.
3. After the next burner cycle, open *Xtreme fork: Last Cycle* and look at its attributes.
