# Stale sensors

*Xtreme profile (fork) → Sensors → Handle stale sensors.* Default off.

## The problem

When the inside sensor stops reporting, for example a Zigbee sensor with an empty battery, SAT should not keep
heating as if nothing happened. SAT 4.2.1 has a check for this (*System configuration →
[Temperature sensor maximum value age](settings-system.md#temperature-sensor-maximum-value-age)*, default
6 hours), but:

- it measures the age from the last **change** of the value, so a sensor that keeps reporting the same
  temperature looks old although it works;
- after that, SAT keeps heating on the heating curve plus the frozen integral of the PID controller, without a
  warning;
- the outside temperature has no age check.

## What the option does

With the option on, SAT-xtreme replaces that check for the inside and outside sensor:

- The age counts from the **last report** of the sensor (`last_reported`), also when it reported the same
  value. A sensor that is *unavailable* or *unknown* is not usable right away.
- The sensors are checked every minute, also when they report nothing.

### Inside temperature

1. When the inside sensor is older than *Maximum age of the inside temperature* (default 90 minutes) and the
   *Backup inside sensor* is up to date, SAT controls on the backup sensor as usual.
2. When no inside sensor is usable, SAT goes into the **safe mode**: it heats on the heating curve only,
   without the correction of the PID controller, and **never above the setpoint it requested at that
   moment**. When it gets warmer outside, the setpoint goes down with the heating curve; when it gets colder,
   it stays at most at that value. The PID controller is left as it is.
3. As soon as a sensor reports again, SAT returns to normal control by itself, and the PID controller
   continues where it was.

After a restart without a usable inside sensor, the setpoint that SAT requests at start-up is the limit.

### Outside temperature

When the outside temperature is older than *Maximum age of the outside temperature* (default 3 hours), SAT
uses the last known value and shows a warning. After a restart there is no last known value yet; then SAT keeps
its last setpoint, as SAT 4.2.1 does.

## Settings

| Option | Default | Range | Details |
|---|---|---|---|
| Handle stale sensors | off | | Turns this on. |
| Maximum age of the inside temperature | 90 min | 10 – 1440 min | Take more than the longest report interval of your sensor (often 1 hour for Zigbee sensors). |
| Backup inside sensor | none | | A second temperature sensor in the same room or a room nearby. |
| Maximum age of the outside temperature | 180 min | 30 – 2880 min | A weather entity is usually updated every hour. |

## What you see

- The binary sensor *Xtreme fork: Stale Sensor* is on while a sensor is stale. Its attributes show the age of
  every sensor in seconds (`inside_age`, `backup_age`, `outside_age`), the inside sensor in use
  (`inside_source`: `main`, `backup` or empty), `safe_mode` with its `setpoint_cap`, and `outside_stale` with
  `outside_last_known`.
- A [repair](repairs.md) appears while the inside or outside sensor is stale and disappears by itself.
- The log has a warning when SAT switches to the backup sensor or the safe mode.

## Turn it on

1. Check in ZHA or Zigbee2MQTT how often your inside sensor reports at least, and choose a maximum age above
   that.
2. *Settings → Devices & services → SAT-xtreme → Configure → Xtreme profile (fork)*.
3. Under *Sensors*, turn on *Handle stale sensors*, choose the ages and optionally a backup sensor, and save.
   SAT reloads.
4. To test it, take the battery out of the inside sensor (or wait for it to drop out): after the maximum age the
   binary sensor goes on and the repair appears.
