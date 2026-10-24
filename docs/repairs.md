# Repairs

SAT-xtreme uses Home Assistant's repairs (*Settings → System → Repairs*) to offer changes that you confirm
with one click. Ignoring a repair leaves everything as it is.

## Create the SAT Xtreme dashboard

Appears when the [dashboard](dashboard.md) does not exist yet. Submit to create it.

## The SAT Xtreme dashboard can be updated

Appears when you turned features on or off and the dashboard was changed by hand, so SAT-xtreme did not
update it automatically. Submit to rebuild it with the cards of the features that are on now; your own
changes to the dashboard are lost. Ignore it to keep your version.

## The boiler ignores the modulation limit

Appears when the [slow calibration](calibration.md) found that the boiler keeps modulating with the maximum
modulation set to 0 %. It shows the modulation that was measured. Submit to turn on
*The boiler ignores the modulation limit* ([ignore modulation limit](modulation-limit.md)); SAT reloads.

## The inside temperature of {name} is stale

Appears with [Stale sensors](stale-sensors.md) on, while the inside sensor has not reported for longer than the
maximum age. SAT-xtreme uses the backup sensor, or heats on the heating curve only. There is nothing to submit:
the repair disappears by itself when the sensor reports again.

## The outside temperature of {name} is stale

Appears with [Stale sensors](stale-sensors.md) on, while the outside temperature has not reported for longer
than the maximum age. SAT-xtreme uses the last known value. The repair disappears by itself.
