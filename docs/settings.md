# Settings

All settings are under *Settings → Devices & services → Smart Autotune Thermostat → Configure*. The menu has
these pages:

| Page | What is on it |
|---|---|
| [General](settings-general.md) | Heating curve, maximum setpoint, PID controller, contact sensors |
| [Presets](settings-presets.md) | Temperatures of the presets |
| [System configuration](settings-system.md) | Duty cycle, cycles per hour, sensor and window timing |
| [Advanced](settings-advanced.md) | Simulation, thermal comfort, dynamic minimum setpoint, modulation, consumption. Only visible when *Advanced mode* is on in your user profile. |
| [Xtreme profile (fork)](settings-xtreme-profile.md) | All features of the fork |
| [PID settings (fork)](settings-pid.md) | Automatic or manual gains, gain factor, maximum rise |

After saving a page, Home Assistant reloads SAT, so the change is active right away. Some fields only
appear when another setting makes them relevant; this is noted per field.

The settings chosen in the [setup wizard](setup-wizard.md) (gateway, sensors, heating system, areas, the
overshoot protection value) are changed with *Reconfigure* on the integration, not on these pages.

!!! tip "Turn on Advanced mode"
    Some pages and fields only appear with *Advanced mode* on. Turn it on in your user profile (click your
    name at the bottom left of Home Assistant).
