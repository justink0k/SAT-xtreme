# Presets

*Configure → Presets*

The SAT climate entity has presets that set its target temperature. Choose them on the thermostat card or
with the action `climate.set_preset_mode`.

| Preset | Default | Range |
|---|---|---|
| Activity | 10 °C | 5 – 35 °C |
| Away | 10 °C | 5 – 35 °C |
| Sleep | 15 °C | 5 – 35 °C |
| Home | 18 °C | 5 – 35 °C |
| Comfort | 20 °C | 5 – 35 °C |

The *Activity* preset is also used while a window is open (see
[Contact sensors](settings-general.md#contact-sensors)). Choosing the preset *None* restores the target
temperature you had before you chose a preset.

## Synchronize climates with preset (sleep / away / activity)

Default off. When on, choosing a preset also sets the target temperature of every
[room](setup-wizard.md#4-areas) that is not off. With *Home*, each room gets back its own target.

## Synchronize with thermostat attached to the boiler

Meant to send SAT's target temperature to the thermostat on the bus as a temporary override (`TC=` on an
OpenTherm Gateway), so the thermostat shows the same target.

!!! bug "Known issue"
    In SAT 4.2.1 (and so far in SAT-xtreme) this option is saved on the options page, but SAT reads it from
    the configuration of the wizard, so turning it on here has no effect.
