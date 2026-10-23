# Installation

SAT-xtreme is installed through [HACS](https://hacs.xyz) as a custom repository. It needs Home Assistant
2025.8 or newer.

!!! note "Its own domain"
    SAT-xtreme uses its own domain, `sat_xtreme`, so it can be installed next to the official SAT, but **do not
    let both control the same boiler**. Coming from the official SAT? See
    [Moving from the official SAT](#moving-from-the-official-sat).

## Install with HACS

1. Open *HACS → ⋮ → Custom repositories*, add `https://github.com/justink0k/SAT-xtreme` with type
   *Integration*, and install **SAT-xtreme**.
2. Restart Home Assistant.
3. Refresh the cache of your browser (Ctrl+Shift+R, or Cmd+Shift+R on a Mac), or reset the frontend cache
   in the companion app. Otherwise the options pages may still show old texts.
4. Add the integration: *Settings → Devices & services → Add integration → SAT-xtreme*, and follow the
   [setup wizard](setup-wizard.md). An OpenTherm Gateway is often discovered automatically.

Updates appear in HACS like any other integration. After every update, restart Home Assistant and refresh
the browser cache again.

## Manual installation

1. Download the source of the [latest release](https://github.com/justink0k/SAT-xtreme/releases/latest).
2. Copy the folder `custom_components/sat_xtreme` into the `custom_components` folder of your Home Assistant
   configuration (create it if it does not exist).
3. Restart Home Assistant and add the integration as above.

## Moving from the official SAT

A configuration of the official *Smart Autotune Thermostat* can be moved to SAT-xtreme with all its settings.

1. Install SAT-xtreme with HACS as above, next to the official SAT, and restart Home Assistant. The official
   SAT keeps heating until the move.
2. Open *Settings → Devices & services → Add integration → SAT-xtreme* and choose **Move a configuration
   from SAT**. Pick the configuration and submit.
3. SAT-xtreme stops the official SAT and takes over within seconds. If you have a thermostat on the bus, it
   covers the short gap.
4. Remove *Smart Autotune Thermostat* in HACS and restart Home Assistant.
5. Change automations and scripts that call `sat.` actions to `sat_xtreme.` (for example
   `sat_xtreme.reset_integral`). Automations that use the entities themselves keep working.

What is kept:

- all settings and options, including the overshoot protection value and the presets;
- the entity IDs and their history, so dashboards and automations that use entities keep working;
- the device and the restored state of the thermostat (mode, target temperature).

If Home Assistant stops in the middle of the move, the move continues on the next start. Ignored discoveries of
the official SAT are not offered for the move.

## Going back to the official SAT

1. If you use the [hot water keep-warm switch](hot_water_keep_warm.md), turn it **on** first, so the gateway
   does not keep keep-warm off.
2. Install the official *Smart Autotune Thermostat* from HACS and set it up again with the wizard (there is
   no automatic move back).
3. Remove SAT-xtreme under *Settings → Devices & services* and in HACS, and restart Home Assistant.

The *SAT Xtreme* dashboard stays until you delete it.
