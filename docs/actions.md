# Actions

Actions (services) of SAT, for scripts and automations. All of them take the SAT climate entity as target.

## sat.reset_integral

Resets the integral part of the PID controller, for example when it has grown too large after a long period
with an open window.

```yaml
action: sat.reset_integral
target:
  entity_id: climate.sat
```

## sat.pulse_width_modulation

Forces [PWM](overshoot-protection.md#pulse-width-modulation-pwm) on or off. SAT may switch it back right after,
when its own decision differs.

```yaml
action: sat.pulse_width_modulation
target:
  entity_id: climate.sat
data:
  enabled: true
```

## sat.start_xtreme_calibration

Fork only, with the [calibration buttons](calibration.md) on. Starts the slow calibration of the overshoot
protection value.

```yaml
action: sat.start_xtreme_calibration
target:
  entity_id: climate.sat
```

## sat.stop_xtreme_calibration

Fork only. Stops the calibration and returns to normal operation.

```yaml
action: sat.stop_xtreme_calibration
target:
  entity_id: climate.sat
```

## sat.create_xtreme_dashboard

Fork only. Creates or rebuilds the [SAT Xtreme dashboard](dashboard.md) with the entities that exist now. Only
changes that dashboard.

```yaml
action: sat.create_xtreme_dashboard
target:
  entity_id: climate.sat
```

!!! note "Fixed in the fork"
    In the official SAT 4.2.1, `sat.reset_integral` and `sat.pulse_width_modulation` silently did nothing when
    the entity ID was given as text, as in most automations. The fork accepts both a single entity ID and a
    list.
