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

Appears when the [calibration](calibration.md) found that the boiler keeps modulating with the maximum
modulation set to 0 %. It shows the modulation that was measured. Submit to turn on
[The boiler ignores the modulation limit](modulation-limit.md); SAT reloads.

## Remove the files of the older SAT-xtreme

Appears after [moving from SAT](installation.md#moving-from-sat) when the files of SAT-xtreme 4.2.1-xtreme.25 or
older are still in `custom_components/sat`. HACS installs the new version in `custom_components/sat_xtreme` and
no longer tracks the old folder. Submit to remove it, then restart Home Assistant. The folder is only removed
when it holds an older SAT-xtreme (checked by its manifest) and no configuration uses it; the official SAT is
never touched.
