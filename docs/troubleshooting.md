# Troubleshooting

## Debug logging

SAT and the fork log their decisions at debug level. The fork's lines start with `Xtreme profile:`,
`Xtreme calibration:` or `SAT-xtreme:`. Turn it on in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.sat_xtreme: debug
```

Or temporarily: *Settings → Devices & services → SAT-xtreme → ⋮ → Enable debug logging*.

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
    [setpoint priming](prime-setpoint.md). If the boiler is anti-cycling (for example after hot water),
    [boiler timing](boiler-timing.md) makes SAT wait for it instead.

??? question "The keep-warm switch has no effect"
    Whether the boiler follows the DHW enable bit depends on the boiler and its settings. On Intergas, the tap
    comfort must be on *Eco* and parameter P074 must be 0. See [Hot water keep-warm](hot_water_keep_warm.md).

??? question "The calibration failed"
    The sensor *Xtreme fork: Calibration* shows the reason in its report: too few valid rounds, a result below
    35 °C, rounds that differ too much, or the 10-hour limit. Open all radiator valves, avoid hot water use and
    try again, preferably on a colder day.

??? question "The wizard calibration gives a strange value (for example 32 °C)"
    The boiler probably ignores the modulation limit. Enter a plausible value by hand, turn on the fork's
    [slow calibration](calibration.md) and run it.

??? question "Sensors are empty after a restart"
    With a gateway over MQTT this is normal for a short time. After a restart or a reload the flame, flow
    temperature, setpoint and modulation show *unknown* or *off* until the gateway sends them again, usually within
    a minute or two, sometimes longer for the return temperature. SAT does not use the old values from before the
    restart. Fixed values of the boiler, such as its capacity, stay available.

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
- **Synchronize with thermostat had no effect.** The option on the Presets page was read from the wrong place;
  it now works.
- **Simulation warning missing.** With *Simulation* on, the log now shows `Simulation mode!`; commands to the
  boiler were already suppressed correctly.
- **Dependency conflict with Home Assistant.** SAT required `pyotgw` 2.2.2 while Home Assistant uses 2.2.3; it
  now requires at least 2.2.3, so it follows Home Assistant.
- **No error reports to the official SAT.** The option *Enable error monitoring* sent errors to the Sentry
  project of the official SAT; the option and Sentry are removed.
- **PID derivative stuck at an old value.** Inside the deadband the derivative kept its last value; it now
  decays to zero. After a restart it starts again instead of using a slope across the downtime.
- **PID reset in a steady room.** A room that stayed at the same temperature for hours lost the integral of the
  PID controller; the reset now only happens when the inside sensor itself stops reporting.
- **Error changes skipped** when they arrived inside the sample time of the PID controller; they are now applied
  at the next control loop.
- **Heating curve rose again in very warm weather**, and its autotune undid its own steps.
- **OpenTherm Gateway restart forgot SAT's commands.** After a restart of the gateway (over MQTT) the boiler ran
  on the thermostat until SAT happened to send each command again, and a maximum setpoint or keep-warm setting
  stayed lost. SAT now sends them again right away, and pauses its control while the gateway is offline.

- **Maximum cycles per hour forgotten after a target change.** A change of the target temperature, or PWM
  turning off for a moment, cleared the list of PWM starts of the last hour, so the limit started from zero. It
  now keeps counting.
- **A room's target change restarted the PWM block.** It now keeps the running on or off phase.
- **Hot water in the PWM blocks.** The hot flow of a hot water burn shaped the length of the next blocks; it now
  does not.
- **Switch mode never turned the switch off.** SAT looked up the state of the switch by its registry ID, found
  nothing and always saw it off; it turned the switch on and never off again. It now reads the switch itself.
- **Old values after a restart.** With a gateway over MQTT, SAT used the values from before the restart (flame,
  flow temperature, setpoint, modulation) as if they were live. They now count only after the first message of the
  gateway. See *Sensors are empty after a restart* above.
- **Messages to an old coordinator after a reload.** Every reload left the MQTT or ESPHome subscriptions of the old
  coordinator running. They now end at the unload.
- **A valve in switch mode got no command.** The setup wizard offers valves, but SAT never opened or closed them. It
  now does.
- **A sensor value that is not a number stopped the control.** A value such as `none`, or a weather entity without
  a temperature, raised an error in every control loop. It now counts as no value, and SAT tries the next outside
  sensor.
- **A missing target temperature stopped the control.** A synchronized thermostat that turned off, or clearing a
  preset without a saved temperature, removed the target of SAT. SAT now keeps the last target.
- **A preset with the same temperature did not show.** Choosing a preset whose temperature equals the current
  target left the old preset in Home Assistant.
- **Underfloor heating got the PID gains of radiators.** The heating system was read from the options, which only
  hold the default *radiators*; the PID now uses the heating system of the setup wizard. With automatic gains
  (version 3) the correction for underfloor heating becomes about 25 % gentler, as intended. A heat pump also gets
  its own choices for *Duty cycles per hour* again.
- **The safe mode of *Handle stale sensors* sent nothing.** Without a usable inside sensor the control loop
  stopped at the missing temperature, so SAT did not heat on the heating curve as described. It now does.

The fixes for the PID controller, the heating curve and the gateway restart come from the fork
[bellini666/SAT](https://github.com/bellini666/SAT).

The full list with versions and files is in
[CHANGES_XTREME.md](https://github.com/justink0k/SAT-xtreme/blob/xtreme/CHANGES_XTREME.md).

## Reporting a problem

Use the [issue tracker of the fork](https://github.com/justink0k/SAT-xtreme/issues), not the one of the official
SAT. For a new boiler preset there is a separate *Boiler preset* template; see
[Boiler presets](boiler_presets.md#adding-a-preset-for-your-boiler).
