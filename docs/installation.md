# Installation

SAT-xtreme is available in the Marketplace (Home Assistant 2026.11 or newer) and in [HACS](https://hacs.xyz)
(older versions). It needs Home Assistant 2025.8 or newer.

!!! note "Its own domain"
    SAT-xtreme uses its own domain, `sat_xtreme`, so it can be installed next to the official SAT, but **do not
    let both control the same boiler**. Coming from the official SAT? See
    [Moving from the official SAT](#moving-from-the-official-sat).

## Install from the Marketplace or HACS

[![Open SAT-xtreme in the Marketplace of your Home Assistant.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=justink0k&repository=SAT-xtreme&category=integration)
[![Add the SAT-xtreme integration to your Home Assistant.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=sat_xtreme)

The first button opens SAT-xtreme in the Marketplace of your Home Assistant (on versions before 2026.11 install
it from HACS as described below); the second starts the setup wizard once it is installed.

1. Open *Settings → Marketplace* (Home Assistant 2026.11 or newer) or HACS (older versions), search for
   **SAT-xtreme** and install it.
2. Restart Home Assistant. In the Marketplace, a repair under *Settings → System → Repairs* offers the restart
   when it is needed.
3. Refresh the cache of your browser (Ctrl+Shift+R, or Cmd+Shift+R on a Mac), or reset the frontend cache
   in the companion app. Otherwise the options pages may still show old texts.
4. Add the integration: *Settings → Devices & services → Add integration → SAT-xtreme*, and follow the
   [setup wizard](setup-wizard.md). An OpenTherm Gateway is often discovered automatically.

Updates appear like any other update: in the Marketplace under *Settings → Updates*, in HACS in its own list.
After every update, restart Home Assistant and refresh the browser cache again.

!!! note "Added as a custom repository before?"
    You do not need to change anything. A custom repository carries over to the Marketplace and keeps getting
    updates.

## Test versions

New versions are often published first as a test version (pre-release). Only take them if you want to help
test:

- **Marketplace:** open *Settings → Devices & services → Marketplace*, open the device of SAT-xtreme, enable its
  *Pre-release* entity (it is disabled by default) and turn the switch on. A specific version can be chosen on
  the page of the repository with *⋮ → Install another version*.
- **HACS:** open SAT-xtreme in HACS, choose *⋮ → Redownload*, turn on *Show beta versions* and choose the version.

Everyone else only gets the stable versions.

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
