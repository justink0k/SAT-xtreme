# Dashboard

SAT-xtreme can create a **SAT Xtreme** dashboard for you. After installing or updating, a repair appears
under *Settings → System → Repairs*: *Create the SAT Xtreme dashboard*. Click submit and the dashboard
appears in the sidebar. To rebuild it later (for example after turning on a feature), press the button
*Xtreme fork: Create Dashboard* or use the action `sat.create_xtreme_dashboard`; this only changes the
SAT Xtreme dashboard.

The dashboard looks up its entities by their unique IDs, so it works whatever they are called. With an
OpenTherm Gateway over MQTT it uses the gateway's own sensors (with their full history and the real burner
start counter); with other gateways it uses SAT-xtreme's own sensors. It shows the current state, graphs of the last hours
(setpoint, flow, modulation, flame, heating demand, hot water), the PID correction, the PWM blocks and
burner starts per day, the learned OPV and the calibration, and leaves out cards of features you do not
use. Only standard Home Assistant cards are used.

The dashboard follows the features you turn on or off: after saving the options it is rebuilt
automatically, as long as you did not change it by hand. If you did, a repair offers the rebuild instead,
so your own changes are never lost without a click.

Creating a dashboard from an integration is not an official Home Assistant API. If it fails, SAT-xtreme
shows the configuration in a notification to paste into a new dashboard by hand.

