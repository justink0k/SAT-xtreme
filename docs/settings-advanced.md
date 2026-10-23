# Advanced

*Configure → Advanced Options*. Only visible when *Advanced mode* is on in your user profile.

## Simulation

Default off. SAT calculates everything but does not send commands to the boiler (OpenTherm over MQTT or
serial), and logs the warning `Simulation mode!` when SAT starts. Useful to watch what SAT would do. Not to be confused with the *Simulated Gateway* of the wizard.

## Thermal Comfort

Default off. SAT uses the *Summer Simmer Index* (the felt temperature, from the room temperature and the
humidity) instead of the room temperature. Needs a humidity sensor in the [wizard](setup-wizard.md#2-sensors).

## Dynamic Minimum Setpoint (Experimental)

Default off. In installations with several rooms, closed valves can make the flow temperature rise above the
overshoot protection value while the boiler burns at minimum power. With this on, SAT adjusts the minimum
setpoint based on the return temperature (or the boiler temperature, see
[Minimum Setpoint Controller Version](settings-general.md#minimum-setpoint-controller-version)), with the
[adjustment factor](settings-general.md#adjustment-factor-for-return-temperature) on the General page.

!!! note
    When the fork's [learned OPV](learned-opv.md) is set to *Learn and apply*, the learned value is used
    to decide on PWM instead.

## Force Pulse Width Modulation

Default off. Always use [PWM](overshoot-protection.md#pulse-width-modulation-pwm), also when the boiler could
burn continuously. Only for OpenTherm (MQTT and serial) and the simulator.

## Minimum Consumption and Maximum Consumption

Default 0. The gas use of the boiler at minimum and maximum power in m³/h, from the manual (range 0 to 8).
When both are filled in, SAT adds the sensor *Current Consumption* (in m³).
Only for OpenTherm (MQTT and serial) and the simulator.

## Climate valve offset

Default 0, range −1 to 1 °C. SAT considers the valve of a [radiator or room](setup-wizard.md#4-areas) open
when its target temperature is at least the room temperature plus this offset.

## Target Temperature Step

Default 0.5 °C, range 0.1 to 1. The step of the target temperature on the thermostat card.

## Maximum Relative Modulation

Default 100 %. The highest modulation SAT lets the boiler use while it is not in PWM. Boilers that
[ignore the modulation limit](modulation-limit.md) do not follow it.

## Sample Time

Default 1 minute. The minimum time between two updates of the PID controller.
