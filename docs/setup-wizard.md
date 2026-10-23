# Setup wizard

The wizard runs when you add the integration (*Settings → Devices & services → Add integration → SAT-xtreme*).
You can run most of it again later with *Reconfigure* on the integration.

!!! tip "Moving from the official SAT"
    If a configuration of the official SAT exists, the first choice is **Move a configuration from SAT**. It skips
    the wizard and keeps all settings; see [Moving from the official SAT](installation.md#moving-from-the-official-sat).

## 1. Choose the gateway

| Choice | For |
|---|---|
| MQTT Gateway | An [OpenTherm Gateway](gateways.md#opentherm-gateway-mqtt) with the OTGW firmware, or [EMS-ESP](gateways.md#ems-esp) |
| Serial Gateway | An [OpenTherm Gateway](gateways.md#opentherm-gateway-serial) reached over a socket, for example `socket://otgw.local:25238` |
| ESPHome | An [ESPHome OpenTherm](esphome.md) device |
| PID Thermostat (PWM On/Off) | A [switch](gateways.md#switch-or-relay) that turns the heating on and off |
| Simulated Gateway | Testing only; visible when *Advanced mode* is on in your user profile |

An OpenTherm Gateway is also discovered automatically (over DHCP or MQTT); then the wizard starts with the
gateway already filled in.

The **name** you give here becomes part of every entity ID, for example `climate.sat` for the name `SAT`.

## 2. Sensors

- **Inside sensor**: the room temperature. A sensor that reports two decimals and updates about every 30
  seconds gives the best results.
- **Outside sensor**: one or more outside temperature sensors or weather entities. With more than one, SAT
  uses the first one that has a value, sensors before weather entities, so a weather entity works as a
  fallback.
- **Humidity sensor** (optional): only needed for *Thermal comfort* (see [Advanced](settings-advanced.md)).

## 3. Heating system

Radiators, heat pump or underfloor heating. This sets the shape of the heating curve and the default
[maximum setpoint](settings-general.md#maximum-setpoint) (55 °C for radiators and heat pumps, 50 °C for
underfloor heating). Not asked for a switch.

## 4. Areas

- **Thermostat**: your physical thermostat, if it is a climate entity in Home Assistant. Its target
  temperature stays in sync with SAT, and it stays the fallback when Home Assistant fails.
- **Radiators**: climate entities (for example thermostatic radiator valves) in the same room as the
  inside sensor.
- **Rooms**: climate entities of other rooms, each with its own target. When a room asks for heat, SAT
  heats too; see [Heating mode](settings-general.md#heating-mode).

Skip this step if SAT is your only thermostat.

## 5. Calibrate the system

For gateways that can send a setpoint (OpenTherm, ESPHome, EMS-ESP), SAT asks how to find the
[overshoot protection value](overshoot-protection.md) (OPV):

- **Calibrate** (about 20 minutes): SAT tries to find the OPV right away. Open all radiator valves first.
  If you have SAT-xtreme, consider the slower and more careful [fork calibration](calibration.md) instead,
  especially when your boiler ignores the modulation limit.
- **Enter the value**: if you already know the OPV.
- **Enter PID values**: skip the OPV and set the PID gains by hand (not recommended).

For a switch, SAT asks whether to use [automatic gains](settings-pid.md#automatic-gains) instead.

!!! note "Fixed in the fork"
    The wizard's choice of automatic or manual gains is now also stored in the options, where SAT reads
    it. In the official SAT 4.2.1 the choice had no effect.

## 6. Manufacturer

SAT suggests the manufacturer of your boiler from the member ID the gateway reports. Check it and change it
if needed. A few manufacturers get special treatment (for example a filter on the reported values for
Geminox), and the fork warns in the log when a [boiler preset](boiler_presets.md) is for another
manufacturer.

## After the wizard

- The climate entity (for example `climate.sat`) appears. Set it to *Heat* to let SAT control the boiler.
- Look at the [settings](settings.md), especially the [heating curve coefficient](settings-general.md#heating-curve-coefficient).
- Create the [dashboard](dashboard.md) from the repair that appears.
- Read [First steps](first-steps.md) before turning on fork features.
