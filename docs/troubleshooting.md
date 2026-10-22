# Troubleshooting

## Debug logging

SAT and the fork log their decisions at debug level. The fork's lines start with `Xtreme profile:`,
`Xtreme calibration:` or `SAT-xtreme:`. Turn it on in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.sat: debug
```

Or temporarily: *Settings → Devices & services → Smart Autotune Thermostat → ⋮ → Enable debug logging*.

When you report a problem, add the relevant part of the log, your gateway and boiler, and the options you
turned on. Remove personal data (addresses, names of rooms you would rather not share).

## Common problems

??? question "The options pages show old texts or miss new options after an update"
    The browser keeps the old texts. Restart Home Assistant and refresh the browser cache (Ctrl+Shift+R, or
    Cmd+Shift+R on a Mac); in the companion app, reset the frontend cache.

??? question "The repair to create the dashboard does not appear"
    It only appears when no dashboard with the address `/sat-xtreme` exists. If you made one yourself with that
    address, use the button *Xtreme fork: Create Dashboard* instead; it replaces the content.

??? question "Graphs on the dashboard are empty"
    New sensors have no history yet; the graphs fill up over the next hours. With an OpenTherm Gateway over
    MQTT the dashboard uses the gateway's own sensors, which do have history.

??? question "The boiler starts minutes after the heating demand"
    With an OpenTherm Gateway and a thermostat on the bus, the setpoint arrives late; turn on
    [Keep the setpoint ready](prime-setpoint.md). If the boiler is anti-cycling (for example after hot water),
    [Align PWM with the boiler](boiler-timing.md) makes SAT wait for it instead.

??? question "The keep-warm switch has no effect"
    Whether the boiler follows the DHW enable bit depends on the boiler and its settings. On Intergas, the tap
    comfort must be on *Eco* and parameter P074 must be 0. See [Hot water keep-warm](hot_water_keep_warm.md).

??? question "The calibration failed"
    The sensor *Xtreme fork: Calibration* shows the reason in its report: too few valid rounds, a result below
    35 °C, rounds that differ too much, or the 10-hour limit. Open all radiator valves, avoid hot water use and
    try again, preferably on a colder day.

??? question "The wizard calibration gives a strange value (for example 32 °C)"
    The boiler probably ignores the modulation limit. Enter a plausible value by hand, turn on the fork's
    [calibration](calibration.md) and run it.

??? question "The room overshoots the target"
    The PID correction is too strong or the heating curve too high. Lower the
    [heating curve coefficient](settings-general.md#heating-curve-coefficient) a little, or lower the
    [gain factor](settings-pid.md#gain-factor).

## Is the failover still working?

The thermostat on the bus is your fallback. To check it with an OpenTherm Gateway in gateway mode: stop Home
Assistant (or the MQTT connection) for a few minutes. Within about a minute the gateway drops SAT's override
and the thermostat controls the boiler again. With [Hand over to the thermostat](handover.md), turning SAT off
does this right away.

## Bug fixes in the fork

These fixes apply to everyone, without an option:

- **Calibration above the maximum setpoint.** The calibration of the official SAT could send 62 °C, above the
  configured maximum, when the boiler reports a higher maximum. It now never exceeds the configured maximum.
- **Automatic gains in the setup wizard had no effect.** The wizard's choice (and manual gains) is now stored
  in the options, where SAT reads it.
- **Prepared for Home Assistant 2026.12**, which no longer supports the update listener SAT used for reloading.
- **ESPHome: hot water and flame read from the right entities** (from the official `develop` branch); see
  [ESPHome](esphome.md).
- **Fixes from the official `develop` branch** that are not in a release yet: the wizard calibration waits for
  the coordinator, the heater command of EMS-ESP, and turning the heater off when all valves close.
- **Sensors or buttons missing after a restart.** The climate entity is now set up first.
- **Actions ignored a single entity.** `sat.reset_integral` and `sat.pulse_width_modulation` now accept an
  entity ID given as text.
- **Home Assistant could hang during the wizard calibration** when the boiler temperature was missing. It now
  waits 15 seconds between checks.
- **Maximum cycles per hour counted per fixed hour.** It now counts the last 60 minutes.
- **Stored dynamic minimum setpoint never loaded** after a restart. It is now loaded.
- **No error reports to the official SAT.** The option *Enable error monitoring* sent errors to the Sentry
  project of the official SAT; the option and Sentry are removed.

The full list with versions and files is in
[CHANGES_XTREME.md](https://github.com/justink0k/SAT-xtreme/blob/xtreme/CHANGES_XTREME.md).

## Reporting a problem

Use the [issue tracker of the fork](https://github.com/justink0k/SAT-xtreme/issues), not the one of the official
SAT. For a new boiler preset there is a separate *Boiler preset* template; see
[Boiler presets](boiler_presets.md#adding-a-preset-for-your-boiler).
