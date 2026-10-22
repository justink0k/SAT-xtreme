# Gateways

SAT reaches the boiler through a gateway. Which one you use decides what SAT can control.

| Gateway | Setpoint | Max. modulation | Hot water setpoint | Fork features |
|---|---|---|---|---|
| [OpenTherm Gateway over MQTT](#opentherm-gateway-mqtt) | yes | yes | yes | all (tested); [hand over](handover.md) and the [keep-warm switch](hot_water_keep_warm.md) only work here |
| [OpenTherm Gateway, serial](#opentherm-gateway-serial) | yes | yes | yes | all except hand over and the keep-warm switch (untested) |
| [ESPHome OpenTherm](esphome.md) | yes | yes | yes | all except hand over and the keep-warm switch (untested) |
| [EMS-ESP over MQTT](#ems-esp) | yes | yes | yes | all except hand over and the keep-warm switch (untested) |
| [Switch or relay](#switch-or-relay) | no (on/off only) | no | no | PID settings, dashboard (untested) |

The fork features were tested with an OpenTherm Gateway over MQTT. With other gateways they should work as
far as the gateway provides the data (flame, modulation, flow temperature), but they have not been tested.

## OpenTherm Gateway (MQTT)

For an [OpenTherm Gateway](https://otgw.tclcode.com/) with the OTGW firmware that publishes over MQTT
(topics like `OTGW/value/<device>/…`). Home Assistant needs the MQTT integration.

In the wizard choose *MQTT Gateway → OpenTherm*, then fill in:

- **Name**: the name of this SAT.
- **MQTT topic**: the *MQTT top topic* from the settings of the OTGW firmware (`OTGW` by default).
- **Device ID**: the device identifier of the gateway, for example `otgw-AC276ECBE4E8`.

SAT sends the gateway commands such as `CS=` (control setpoint), `CH=` (heating on or off), `MM=` (maximum
modulation) and `SW=` (hot water setpoint).

### Gateway mode and a thermostat on the bus

The OpenTherm Gateway can sit between the boiler and your existing thermostat (*gateway mode*). This is the
safest setup: when Home Assistant stops, the gateway drops SAT's overrides after about a minute and the
thermostat on the bus takes over again.

In gateway mode the gateway only replaces the control setpoint **inside the messages of the thermostat**.
A thermostat that sends the setpoint rarely (a Nest: about every 150 seconds) therefore delays every new
setpoint. The fork's [Keep the setpoint ready](prime-setpoint.md) avoids that delay, and
[Hand over to the thermostat](handover.md) gives control back right away when you turn SAT off.

!!! tip "Use the PIC firmware in gateway mode"
    The fork was tested with the PIC firmware of the gateway in gateway mode (`GW=1`). In monitor mode the
    gateway cannot change anything.

## OpenTherm Gateway (serial)

For an OpenTherm Gateway reached over a serial connection or a network socket. In the wizard choose *Serial
Gateway* and fill in the URL, for example `socket://otgw.local:25238`. Home Assistant can discover a gateway
named `otgw` on your network automatically.

## ESPHome

For a board with the [ESPHome OpenTherm component](https://esphome.io/components/opentherm.html). The entities
must have exactly the names SAT expects; see [ESPHome](esphome.md) for a minimal configuration.

## EMS-ESP

For Bosch, Buderus, Nefit and other EMS boilers with [EMS-ESP](https://emsesp.org/) over MQTT. In the wizard
choose *MQTT Gateway → EMS-ESP* and fill in the MQTT topic of EMS-ESP (`ems-esp` by default).

## Switch or relay

*PID Thermostat (PWM On/Off)* controls any `switch` or `input_boolean` that turns the heating on and off,
for example a relay on the thermostat contacts of a boiler, or an electric heater. SAT cannot set a water
temperature, so it always uses [PWM](overshoot-protection.md#pulse-width-modulation-pwm): the PID output
decides how long the switch stays on in each block.

The *Temperature setting* in the wizard is the water temperature the boiler makes when it is on (for
electric heating: 100).

## Simulator

The *Simulated Gateway* simulates a boiler for testing and development. It is only offered when *Advanced
mode* is on in your user profile. Do not use it to heat a house.
