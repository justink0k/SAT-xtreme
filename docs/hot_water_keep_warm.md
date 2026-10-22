# Hot water keep-warm at night

The keep-warm (comfort) function of many combi boilers fires the burner for a few seconds now and then
to keep the hot water ready. Each of those short burns starts the anti-cycling time of the boiler, so it
also delays the next heating block. With the keep-warm switch you decide when that is worth it, for
example only during the day:

```yaml
- alias: "Hot water keep-warm off at night"
  triggers:
    - trigger: time
      at: "23:00:00"
  actions:
    - action: switch.turn_off
      target:
        entity_id: switch.xtreme_fork_hot_water_keep_warm_sat

- alias: "Hot water keep-warm on in the morning"
  triggers:
    - trigger: time
      at: "06:30:00"
  actions:
    - action: switch.turn_on
      target:
        entity_id: switch.xtreme_fork_hot_water_keep_warm_sat
```

How it works: the OpenTherm Gateway command `HW=0` clears the DHW enable bit that goes to the boiler,
and `HW=A` gives that bit back to the thermostat on the bus (normal operation). The switch only sends
these commands; it never changes the hot water setpoint. **Whether the boiler follows the bit depends on
the boiler and its settings.**

- **Intergas:** the tap comfort function has three settings: *On* (always keep warm), *Eco* (self-learning:
  no keep-warm at night and when you are away) and *Off*. According to the Intergas manual, keep-warm can
  only be switched through OpenTherm when the tap comfort is set to **Eco** and parameter **P074**
  (number of Eco days, factory value 7) is **0**. With *On*, or with a self-learning *Eco* (P074 above
  0), the boiler ignores the bit and this switch has no effect. If the self-learning *Eco* already does
  what you want, you do not need this switch at all.
- Other boilers: check the manual for how the boiler treats the DHW enable bit of OpenTherm.
- With the switch off, hot water still came out of the tap on the tested Intergas Xtreme 30, it only
  takes longer. Some boilers may block hot water completely when the DHW enable bit is off: test this
  first.
- If the thermostat on the bus itself turns hot water off (for example a hot water schedule), the
  switch on (`HW=A`) follows that thermostat.
- The gateway keeps the last setting, also when Home Assistant is down. Turning the option off sends
  `HW=A` once; turn the switch on before you remove SAT-xtreme.
- The entity ID of the switch depends on the name of your SAT (and sometimes the area of the device);
  look it up under *Settings → Entities* and replace `switch.xtreme_fork_hot_water_keep_warm_sat` in the
  example.

