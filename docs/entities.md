# Entities

The entity IDs depend on the name you gave SAT in the wizard (and sometimes on the area of the device). The
examples below use the name `SAT`. Look up your own IDs under *Settings → Entities*, filtered on the
integration.

## Climate

| Entity | Example ID | What it is |
|---|---|---|
| The SAT thermostat | `climate.sat` | Turn on (*Heat*) and off, set the target temperature and presets. |

Useful attributes of the climate entity:

| Attribute | Meaning |
|---|---|
| `setpoint` | The control setpoint SAT asks for. |
| `error` | Target minus room temperature. |
| `pid_output` | The PID correction on top of the heating curve. |
| `proportional`, `integral`, `derivative` | The P, I and D parts of the correction. |
| `current_kp`, `current_ki`, `current_kd` | The gains in use. |
| `automatic_gains` | Whether automatic gains are on. |
| `pulse_width_modulation_enabled` | Whether SAT uses PWM right now. |
| `valves_open` | Whether a radiator or room valve is open. |
| `rooms` | The target temperatures of the rooms. |
| `xtreme_pid_gain_factor`, `xtreme_maximum_setpoint_rise` | The fork's [PID settings](settings-pid.md). |

## Sensors of the official SAT

| Entity | When | Shows |
|---|---|---|
| *Heating Curve* | always | The water temperature from the heating curve. |
| *Error Value* | always | Target minus room temperature. |
| *Boiler Manufacturer* | always | The manufacturer SAT uses. |
| *Flame Status* | always | The health of the flame (for example healthy, short cycling). |
| *Boiler Status* | always | What the boiler is doing according to SAT. |
| *Current Power (Boiler)* | when the modulation limit is managed, or with [Ignore modulation limit](modulation-limit.md) | The current heating power in kW. |
| *Current Consumption (Boiler)* | with the power sensor and both [consumption values](settings-advanced.md#minimum-consumption-and-maximum-consumption) | Gas use. |

With a serial OpenTherm Gateway or the simulator, SAT adds more sensors with the raw boiler data.

## Binary sensors of the official SAT

The *Synchro* sensors are problem sensors: they turn on when the mismatch lasts longer than 60 seconds.

| Entity | When | On means |
|---|---|---|
| *Control Setpoint Synchro* | gateways that set a setpoint | The boiler does not have the setpoint SAT asked for (a problem). |
| *Relative Modulation Synchro* | when the modulation limit is managed | The boiler does not have the modulation SAT asked for. |
| *Central Heating Synchro* | always | Whether the boiler heats differs from what the SAT thermostat shows (heating or idle). |
| *Boiler Health*, *Flame Health* | always | A problem with the boiler or flame data. |
| *Window Sensor* | with [contact sensors](settings-general.md#contact-sensors) | A window or door is open. |

## Number

| Entity | When | What it is |
|---|---|---|
| *Hot Water Setpoint (Boiler)* | gateways that support it | The hot water temperature of the boiler. Changing it sends a new hot water setpoint. |

## Entities of the fork

All names start with **Xtreme fork:**.

| Entity | When | Shows |
|---|---|---|
| *PID Output* | always | The PID correction on top of the heating curve, with the P, I and D parts and the gains. |
| *Boiler Flow* | always | The flow temperature as SAT sees it. |
| *Control Setpoint* | always | The setpoint the boiler has. |
| *Boiler Modulation* | always | The modulation the boiler reports. |
| *Burner Starts* | always | Burner starts counted by SAT (kept across restarts). |
| *Flame* | always (binary) | The flame is on. |
| *Hot Water Active* | always (binary) | The boiler is making hot water. |
| *Heating Demand* | always (binary) | SAT asks the boiler for heat. |
| *Create Dashboard* | always (button) | Creates or rebuilds the [dashboard](dashboard.md). |
| *PWM Burn Time* | [Boiler timing](boiler-timing.md) | Burn time of the last PWM block, with the planned on time. |
| *Anti-cycling Remaining* | [Boiler timing](boiler-timing.md) | Seconds until the boiler may start again. |
| *Learned OPV* | [Learned OPV](learned-opv.md) not *Off* | The learned OPV, with its samples. |
| *Calibration* | [Slow calibration](calibration.md) | Phase, progress and report of the calibration. |
| *Start Calibration*, *Stop Calibration* | [Slow calibration](calibration.md) (buttons) | Start or stop the calibration. |
| *Hot Water Keep Warm* | [Keep-warm switch](hot_water_keep_warm.md) (switch) | On: normal (`HW=A`); off: no keep-warm (`HW=0`). |
| *Setpoint Chain* | [Setpoint chain](setpoint-chain.md) | The calculated setpoint, with the sent and received setpoint as attributes. |
| *Last Cycle* | [Burner cycles](burner-cycles.md) | Burn time of the last burner cycle, with its data. |
| *Cycles Last Hour*, *Cycles Last 24h* | [Burner cycles](burner-cycles.md) | Number of burner cycles in the window. |
| *Average Burn Time Last Hour*, *Average Burn Time Last 24h* | [Burner cycles](burner-cycles.md) | Average burn time in the window. |

The unique IDs of the fork's entities contain `-xtreme-`, so they never clash with entities of the official SAT.
