# ESPHome

SAT can control a boiler through a board with the
[ESPHome OpenTherm component](https://esphome.io/components/opentherm.html). In the wizard choose *ESPHome*
and select the ESPHome device.

!!! important "Use these exact names"
    SAT finds the entities of the ESPHome device by their names. Use the names below, otherwise SAT cannot
    find them in Home Assistant.

```yaml
# Insert the usual ESPHome configuration (board, api, ota, etc.)

opentherm:
  in_pin: # insert in pin
  out_pin: # insert out pin
  ch_enable: true
  dhw_enable: true

number:
  - platform: opentherm
    t_dhw_set:
      name: t_dhw_set
      step: 1
      restore_value: true
      initial_value: 45
    t_set:
      name: t_set
      restore_value: true
      initial_value: 10
    max_t_set:
      name: max_t_set
      step: 1
      restore_value: true
    max_rel_mod_level:
      name: max_rel_mod_level
      min_value: 0
      max_value: 100
      step: 1
      initial_value: 100
      restore_value: true

sensor:
  - platform: opentherm
    rel_mod_level:
      name: rel_mod_level
    device_id:
      name: device_id
    t_boiler:
      name: t_boiler
    t_ret:
      name: t_ret
    max_capacity:
      name: max_capacity
    min_mod_level:
      name: min_mod_level
    t_dhw_set_lb:
      name: t_dhw_set_lb
    t_dhw_set_ub:
      name: t_dhw_set_ub

binary_sensor:
  - platform: opentherm
    flame_on:
      name: flame_on
    dhw_active:
      name: dhw_active

switch:
  - platform: opentherm
    dhw_enable:
      name: dhw_enable
    ch_enable:
      name: ch_enable
```

!!! note "Changed in SAT-xtreme 4.2.1-xtreme.18"
    Hot water is now read from the `dhw_active` binary sensor (it used the hot water *enable* switch) and
    the flame from the binary sensor domain. These fixes come from the official SAT `develop` branch. If
    you used SAT with ESPHome before, add the `dhw_active` binary sensor to your configuration.

See the [ESPHome OpenTherm documentation](https://esphome.io/components/opentherm.html) for the other
entities the component offers.
