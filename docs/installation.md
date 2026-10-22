# Installation

SAT-xtreme is installed through [HACS](https://hacs.xyz) as a custom repository. It needs Home Assistant
2025.8 or newer.

!!! warning "Not together with the official SAT"
    The fork and the official SAT use the same domain (`sat`), so they **cannot be installed at the same
    time**. An update of the official version would overwrite the fork.

## Install with HACS

1. In HACS, remove the official *Smart Autotune Thermostat* (or make sure it is not installed).
2. Open *HACS → ⋮ → Custom repositories*, add `https://github.com/justink0k/SAT-xtreme` with type
   *Integration*, and install **SAT-xtreme**.
3. Restart Home Assistant.
4. Refresh the cache of your browser (Ctrl+Shift+R, or Cmd+Shift+R on a Mac), or reset the frontend cache
   in the companion app. Otherwise the options pages may still show old texts.
5. Add the integration: *Settings → Devices & services → Add integration → Smart Autotune Thermostat*, and
   follow the [setup wizard](setup-wizard.md). An OpenTherm Gateway is often discovered automatically.

Updates appear in HACS like any other integration. After every update, restart Home Assistant and refresh
the browser cache again.

## Manual installation

1. Download the source of the [latest release](https://github.com/justink0k/SAT-xtreme/releases/latest).
2. Copy the folder `custom_components/sat` into the `custom_components` folder of your Home Assistant
   configuration (create it if it does not exist).
3. Restart Home Assistant and add the integration as above.

## Coming from the official SAT

Your configuration is kept: the domain and the configuration format are the same, so the overshoot
protection value, presets and all other settings stay as they are. Remove the official SAT in HACS,
install SAT-xtreme as above and restart. Nothing of the fork is turned on until you do so yourself.

After the restart, a repair appears under *Settings → System → Repairs* that offers to create the
[dashboard](dashboard.md).

## Moving from SAT

From 4.2.1-xtreme.26, SAT-xtreme uses its own domain, `sat_xtreme`, so it can be listed in HACS and installed
next to the official SAT. A configuration of the official SAT, or of SAT-xtreme 4.2.1-xtreme.25 or older (both
use the domain `sat`), can then be moved with all its settings:

1. Update SAT-xtreme in HACS as usual and restart Home Assistant. The old configuration keeps running.
2. Open *Settings → Devices & services → Add integration → SAT-xtreme* and choose **Move a configuration
   from SAT**. Pick the configuration and submit.
3. SAT-xtreme stops the old configuration and takes over within seconds. If you have a thermostat on the bus,
   it covers the short gap.
4. Remove the old SAT-xtreme entry (or the official *Smart Autotune Thermostat*) in HACS and restart Home
   Assistant.
5. Change automations and scripts that call `sat.` actions to `sat_xtreme.` (for example
   `sat_xtreme.reset_integral`).

All settings and options (including the overshoot protection value and the presets), the entity IDs and their
history, the device, the learned OPV, the calibration report, the keep-warm state and the
[dashboard](dashboard.md) are kept.

## Going back to the official SAT

1. Turn off the options under *Configure → Xtreme profile (fork)* (optional, but it makes the switch-over
   clean). If you use the [hot water keep-warm switch](hot_water_keep_warm.md), turn it **on** first, so
   the gateway does not keep keep-warm off.
2. In HACS, remove the custom repository `https://github.com/justink0k/SAT-xtreme`.
3. Install the official *Smart Autotune Thermostat* from HACS and restart Home Assistant.

The extra options of the fork are ignored by the official version. The *SAT Xtreme* dashboard stays until
you delete it.
