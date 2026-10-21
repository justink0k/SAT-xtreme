# Boiler presets – research notes

Research for a future "Boiler preset" option in the SAT-xtreme fork. Every value has a source. Values
without a reliable source are marked **unknown** and must not go into a preset.

Status: collected 2026-10-21. The fork ships one preset (Intergas Xtreme 30 (2024)); the other models
below are research notes, not presets. New presets come from users who own the boiler.

## What a preset would contain

| Field | Why SAT needs it | Notes |
|---|---|---|
| Minimum heating output (Pn min, 80/60 °C) | PWM decisions, power sensor fallback | Fixed per model. The most important value for low-load behaviour. |
| Maximum heating output (Pn max, 80/60 °C) | power sensor fallback | Many boilers let the installer lower the maximum (see below), so this is the model maximum, not necessarily the installed value. |
| Anti-cycling time | step 3: minimum off phase, wait after hot water | Varies a lot per brand, and on some boilers it depends on the flow temperature. |
| Ignores the modulation limit (MM=) | step 2 | No manufacturer documents this; only community knowledge. |

Not in a preset: the overshoot protection value (OPV). It depends on the house and the radiators,
not on the boiler, so it stays learned or calibrated per installation.

## Results per model

Natural gas, central heating, 80/60 °C unless noted. "min – max" in kW.

| Brand / series | Model | Pn min – max (80/60) | Anti-cycling | Source |
|---|---|---|---|---|
| Intergas Xtreme | Xtreme 30 (2024) | 3.9 – 19.5 | 5 min (parameter P036, factory value) | Rating plate of a 2024 unit (G25.3), P036 value from the installer settings of the same unit. Public installation manual not found. |
| Intergas Xtreme | Xtreme 36 | ? – 32.1 (load Hi 3.6 – 32.7) | 5 min (P036, assumed same platform) – **to verify** | [Intergas product page](https://www.intergas-verwarming.nl/en/trade/products/xtreme/xtreme-36/) |
| Nefit ProLine NxT | HRC 24/CW3, HRC 24/CW4 | 5.7 – 22.8 | 10 min (status 0A 202: "more than once per 10 minutes a heat demand"); not adjustable in the menu | Nefit installation instructions 6721823664 (2023/12), tables 15.2 and 36 ([PDF](https://portal.insmart.nl/downloads/prolineNxtInstallatiehandleiding.pdf)) |
| Nefit ProLine NxT | HRC 30/CW5 | 6.4 – 27.8 | 10 min (as above) | same |
| Remeha Calenta Ace | 25ds / 28c | 5.0 – 24.8 (28c factory-limited to 19.9) | exists (status "AntiCyclus"), duration not documented – **unknown** | Remeha installation and service manual Calenta Ace 25ds-28c-35ds-40c, tab. 3 ([PDF](https://portal.insmart.nl/downloads/remeha_calenta_ace_Installatie-%2Ben%2Bservicehandleiding%2BCalenta%2BAce%2B25ds-28c-35ds-40c.pdf)) |
| Remeha Calenta Ace | 35ds / 40c | 7.0 – 34.5 (40c factory-limited to 24.8) | as above – **unknown** | same |
| Vaillant ecoTEC plus | VC 15CS/1-5 | 2.5 – 14.8 (G20) | up to 20 min, **depends on the flow temperature** (d.02, 2 – 60 min) | Technical data: [Vaillant BE brochure 0020277106 (09/19)](https://www.vaillant.be/telechargements/brochures/vai-196-com-fr-ecotec-plus-b2b-2806479.pdf); anti-cycling: [ecoTEC plus installation instructions 0020244998_06 (2021), §10.1](https://professional.vaillant.co.uk/downloads/product-manuals/ecotec-plus-1/ecotec-plus-storage-combi-installation-instructions-2422737.pdf) |
| Vaillant ecoTEC plus | VC 25CS/1-5 | 3.5 – 25.0 (G20) | as above | same |
| Vaillant ecoTEC plus | VC 35CS/1-5 | 4.0 – 34.8 (G20) | as above | same |
| Viessmann Vitodens 100-W | B1HF 11 / 19 / 25 / 32 kW | 2.9 – 10.1 / 17.5 / 23.0 / 29.3 | **unknown** | [Viessmann datasheet 6195357 GB 4/2023](https://dam.cityplumbing.co.uk/private/xwg25do/GPID_1500069169_TECH_00.pdf) |
| ATAG i-Serie | i32EC (Belgium) | 6.1 – 28.3 (G20); 5.0 – 23.1 (G25) | 5 min after a shut-off at the setpoint; 2 min wait after hot water | [ATAG installation manual 8H.51.92.00 (09.17)](https://atag.compano.com/Data/Environments/000001/Attachment/Bijlage/Pictures/Overzicht%20Productgroepen/8H519200%20INST%20MANUAL%20i-%20SERIE%20COMFORT%20NL-F%20A5%20V0917.pdf), p. 52 and 112 |
| ATAG i-Serie | i28CZ / i36CZ (Netherlands) | 4.9 – 24.3 / 6.7 – 31.1 at **50/30** (80/60 not published) | 5 min (as above, same series) | [ATAG factsheet i-Serie](https://www.atagverwarming.nl/getmedia/88607961-a904-4b22-b4ad-6edb02bc61fb/Factsheet-ATAG-i-Serie.pdf) |
| Wolf CGB-2 | CGB-2-14 / -20 / -24 | 1.8 – 13.5 / 3.8 – 18.9 / 4.8 – 23.8 | 7 min (HG09, 1 – 30 min) | [Wolf Montageanleitung CGB-2 3063421_201512](https://www.heizungsdiscount24.de/pdf/Wolf-CGB-2-14-8615008_10_Montageanleitung-Gasbrennwerttherme-Wolf-CGB-2-2K.pdf), p. 8 and parameter table |

Not found with a usable source (yet): Bosch Condens / Buderus GB172i, Worcester Greenstar, Ideal Logic,
Baxi, Ariston, Immergas, Ferroli, Sime, Itho Daalderop, De Dietrich, Brötje.

## Ignores the modulation limit (MM=)

No manufacturer documents whether its boiler honours the maximum relative modulation setting
(OpenTherm MsgID 14). What exists:

- Upstream SAT treats Ideal, Intergas, Geminox and Nefit as boilers without usable relative modulation
  (`coordinator.py`), and the OTGW firmware copies that list (`SAT_QUIRK_NO_REL_MOD` in `SATtypes.h`).
- Measured on one Intergas Xtreme 30: MsgID 14 is answered with Data-Invalid and `MM=0` is ignored
  (it modulates up to 100 %), while the relative modulation level (MsgID 17) is reported correctly.

So the upstream list says "no relative modulation", while the measurement says "modulation reported,
limit ignored". A preset should therefore not set this switch from the brand alone; it should be
measured (see "Ketelgedrag zelf herkennen" in the roadmap: detect Data-Invalid on MsgID 14).

## Findings that matter for the design

1. **Anti-cycling is not one number.** It ranges from 5 minutes (Intergas, ATAG) via 7 (Wolf) and 10
   (Nefit) to up to 20 minutes on Vaillant, where the effective time also depends on the flow
   temperature (at a 45 °C target and the default setting it is 11.5 minutes). A preset can fill in
   the default, but the option must stay editable, and Vaillant would need a flow-dependent table.
2. **The installed maximum is often lower than the model maximum.** Nefit, Remeha (GP007) and Wolf let
   the installer limit the heating power, and Remeha ships some models limited (28c at 19.9 kW, 40c at
   24.8 kW). The minimum is fixed per model, and that is the value that matters for PWM.
3. **Test conditions differ.** Values are given at 80/60 °C or 50/30 °C and for G20 or G25 gas (the
   Netherlands uses G25.3, which gives lower numbers). A preset needs one consistent basis: 80/60 °C
   with the gas of the country, as on the rating plate.
4. **Not every boiler speaks OpenTherm natively.** Vaillant and Wolf use eBus and need an OpenTherm
   module; Nefit/Bosch use EMS. SAT can still control them through such a module or EMS-ESP, but the
   behaviour (and the anti-cycling) may differ from what the manual describes for the native bus.
5. **The rating plate is the best source for a specific unit.** The fork's option description should
   say so, and the preset only fills in the defaults.

## Adding a preset for your boiler

Open an issue with the **Boiler preset** template on the
[issue tracker of the fork](https://github.com/justink0k/SAT-xtreme/issues/new/choose). It asks for:

1. Brand, model and year of manufacture, gas type and country.
2. The rated heating output for central heating (Pn, 80/60 °C), minimum and maximum, from the
   **rating plate**, with a photo of the plate.
3. The factory anti-cycling time and the name of the parameter, with the manual (title, document
   number, version, page) as source.
4. Optionally: whether the boiler ignores the maximum modulation (`MM=`). On an OpenTherm Gateway you
   can see this in the log: MsgID 14 is answered with Data-Invalid, or the reported modulation stays
   above the limit you set.

A preset is added to `BOILER_PRESETS` in `custom_components/sat/xtreme_profile.py` with its source, and
only fills in numbers: it never turns a switch on or off.
