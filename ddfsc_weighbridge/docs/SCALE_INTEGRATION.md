# Weighbridge Scale Integration — Master-K IDé 500 → Odoo

The indicator stays the legal weighing instrument (its printer and DSD alibi memory keep working).
A small program, the **scale bridge**, runs on a PC next to the indicator, reads the weight the
indicator sends, and pushes it to Odoo. On the weighbridge ticket the operator presses
**Capture First Weight from Scale** / **Capture Second Weight from Scale** instead of typing.

```
IDé 500 ──RS-232 (COM1/COM2) or USB──► weighbridge PC: scale_bridge.py ──HTTP (LAN)──► Odoo server
   └── parallel port ──► existing slip printer (unchanged)
```

## What Odoo does

- **Weighbridge ▸ Scales** (managers): one record per weighbridge — code `WB1` is created on
  install ("Main Weighbridge (Master-K IDé 500)"). Shows *Online*, last weight, stable, time, DSD
  number and the raw frame. *Reading valid for* (10 s) and *minimum weight* (20 kg) are set here.
- **Ticket**: Scale field, *Scale Online* indicator, capture buttons, and for each weighing its
  **source** (From Scale / Typed) and **DSD number**.
  - Capture refuses a reading that is older than the validity, not stable, or below the minimum
    (empty platform).
  - Typed weights are still possible (bridge down, power cut) but are marked *Typed*, noted in the
    chatter, and the ticket still needs the photo of the printed slip before completion.
  - When **both** weights come from the scale, the ticket can be completed without the slip photo:
    the DSD numbers tie Odoo to the indicator's alibi memory.
- Only a user in the group **Weighbridge ▸ Scale Device (bridge program only)** can send readings.

## Hardware connection (what we saw on the back of the indicator)

| Port on the IDé 500 | Use |
|---|---|
| **COM1 / COM2** (DB9, RS-232) | Recommended. Connect to the PC with a null-modem RS-232 cable, or through a USB–RS-232 adapter (FTDI/Prolific) if the PC has no COM port. |
| **USB** (type B) | Often appears on the PC as a virtual COM port — try it if the driver is available. |
| ETHERNET (blank plate) | Option card not fitted; only usable if Master-K installs it (`connection = tcp`). |
| Parallel (printer) | Keep for the slip printer. |
| 1 MASTER CAN 6 | Not used. |

In the indicator's **F6 Management menu**, set the serial port used by the PC to **continuous
transmission** of the gross/net weight (or *on request*), and note the speed and format
(typically **9600 baud, 8 data bits, no parity, 1 stop bit**). If the menu is locked, the Master-K
technician or the weights-and-measures seal holder sets it — the metrological settings are not
touched, only the communication port.

## Set-up on the weighbridge PC (Windows)

1. Install Python 3 (python.org, tick "Add to PATH"), then `pip install pyserial`.
2. Copy the folder `ddfsc_weighbridge/tools/` to `C:\DDFSC\scale\`.
3. In Odoo (admin): create a user **weighbridge.device**, groups: only *Weighbridge ▸ Scale Device*;
   log in as it once and create an **API key** (My Profile ▸ Account Security ▸ New API Key).
   Odoo limits API keys of normal users to **90 days**: renew the key before it expires (or ask the
   administrator to raise the limit for this account), otherwise the bridge stops with
   "Odoo refused the login".
4. Copy `scale_bridge.ini.example` to `scale_bridge.ini`, set `url` (Odoo server address on the
   LAN), `api_key`, the COM `port` and the serial settings.
5. Find the port: `python scale_bridge.py --list-ports`.
6. **Sniff** the frames (nothing is sent to Odoo):
   `python scale_bridge.py --config scale_bridge.ini --sniff`
   Put a known weight on the bridge (or watch the empty platform). You should see lines such as
   `'ST,GS,+0038760kg'`. Then:
   - the weight is taken as the **last number** in the frame; if that is wrong, set `weight_regex`
     (one group around the number);
   - if the frame has a motion flag (e.g. `US` unstable / `ST` stable) set `motion_marker = US`,
     otherwise stability = the same value 3 times in a row (`stable_repeats`);
   - if the frame carries the DSD number, `dsd_regex` picks it up;
   - if nothing arrives, the port only answers on request: set `poll_command` (from the indicator
     manual, e.g. `\x05` or `P\r\n`).
   Send the sniff output to the developer if in doubt — tuning is a one-line change.
7. Run it: `python scale_bridge.py --config scale_bridge.ini`. In Odoo, Weighbridge ▸ Scales shows
   **Online** and the live weight.
8. Start it automatically: Task Scheduler ▸ *Create Task* ▸ trigger *At startup*, action
   `pythonw.exe C:\DDFSC\scale\scale_bridge.py --config C:\DDFSC\scale\scale_bridge.ini`,
   "Run whether user is logged on or not", restart on failure every minute.

The bridge reconnects by itself when the cable, the indicator or Odoo goes away, and keeps the
scale "online" with a reading every 2 s while the weight does not change.

## Demo without hardware

`python scale_bridge.py --config scale_bridge.ini --simulate` sends a simulated truck
(0 → 38 760 kg loaded → 15 240 kg empty → 0, settling each time). Open a ticket, press
*Capture First Weight from Scale* while it shows 38 760 kg, then *Capture Second Weight* at
15 240 kg: net 23 520 kg.

## Troubleshooting

| Symptom | Check |
|---|---|
| Ticket says "No recent reading" | Bridge running? PC on the LAN? `url` right? Look at the log file. |
| "Odoo refused the login" | Device login / API key; the user must be active. |
| "The weight is not stable yet" | Wait for the indicator's stability sign; or tune `motion_marker` / `stable_repeats`. |
| Wrong numbers (×10, decimals) | `scale_factor`, or `weight_regex`. |
| Nothing in `--sniff` | Port, cable (null-modem), baud rate, or the port is set to "on request" (`poll_command`). |
| Negative values (e.g. −20 kg) | Normal zero drift on an empty platform; readings below *minimum weight* are refused. |
