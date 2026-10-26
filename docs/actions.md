# Actions

Actions (services) of SAT, for scripts and automations. All of them take the SAT climate entity as target.

!!! note "Coming from the official SAT"
    The actions of SAT-xtreme start with `sat_xtreme.`; those of the official SAT with `sat.`. After
    [moving](installation.md#moving-from-the-official-sat), change automations and scripts that call `sat.` actions.

!!! info "Events"
    With [Burner cycles](burner-cycles.md) on, SAT-xtreme fires the events `sat_xtreme_cycle_started` and
    `sat_xtreme_cycle_ended`.

## sat_xtreme.reset_integral

Resets the integral part of the PID controller, for example when it has grown too large after a long period
with an open window.

```yaml
action: sat_xtreme.reset_integral
target:
  entity_id: climate.sat
```

## sat_xtreme.pulse_width_modulation

Forces [PWM](overshoot-protection.md#pulse-width-modulation-pwm) on or off. SAT may switch it back right after,
when its own decision differs.

```yaml
action: sat_xtreme.pulse_width_modulation
target:
  entity_id: climate.sat
data:
  enabled: true
```

## sat_xtreme.start_xtreme_calibration

Fork only, with the [slow calibration](calibration.md) buttons on. Starts the slow calibration of the overshoot
protection value.

```yaml
action: sat_xtreme.start_xtreme_calibration
target:
  entity_id: climate.sat
```

## sat_xtreme.stop_xtreme_calibration

Fork only. Stops the calibration and returns to normal operation.

```yaml
action: sat_xtreme.stop_xtreme_calibration
target:
  entity_id: climate.sat
```

## sat_xtreme.create_xtreme_dashboard

Fork only. Creates or rebuilds the [SAT Xtreme dashboard](dashboard.md) with the entities that exist now. Only
changes that dashboard.

```yaml
action: sat_xtreme.create_xtreme_dashboard
target:
  entity_id: climate.sat
```

## sat_xtreme.try_opv_offset

Fork only, with *Choose the OPV from a model* on. Uses the OPV `offset` degrees lower (negative) or higher
(positive) for `hours` hours, also with *Learn only*, and goes back by itself. The attributes `test` and
`last_test` of *Learned OPV* show the predicted and the real burn time. See
[Checking the model](learned-opv.md#checking-the-model).

| Field | Range |
|---|---|
| `offset` | −3 to +3 °C |
| `hours` | 1 to 72 |

```yaml
action: sat_xtreme.try_opv_offset
target:
  entity_id: climate.sat
data:
  offset: -1
  hours: 24
```

!!! note "Fixed in the fork"
    In the official SAT 4.2.1, `sat.reset_integral` and `sat.pulse_width_modulation` silently did nothing when
    the entity ID was given as text, as in most automations. The fork accepts both a single entity ID and a
    list.
