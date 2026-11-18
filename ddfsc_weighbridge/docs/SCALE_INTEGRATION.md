# Weighbridge Integration — Master-K IDé 500 → Odoo

Source: *IDe 500 Weigh Bridge / Scale Software technical manual* (Master-K / Arpège, 03/02/09)
and the IDé 500 data sheet, both in `Downloads/AyuGram Desktop/`.

## How it works (no screen needed)

The indicator does not run software that a PC "opens" and it has no display output to a computer —
that is what the server-room colleague meant. What it **does** have are serial ports that send
**text**. Nothing is shown on the PC; a small background program (the *scale bridge*) listens on
the port and forwards what arrives to Odoo.

```
 IDé 500 ── COM1 (RS-232, DB9) ──► weighbridge PC: scale_bridge.py (background) ── LAN ──► Odoo
    └── LPT ──► existing slip printer (unchanged)
```

Alternative without a PC at the weighbridge: a **serial-to-Ethernet converter** (e.g. Moxa NPort
5110, USR-TCP232) plugged into COM1 gives the port an IP address; the bridge then runs on the Odoo
server with `connection = tcp`.

### Recommended mode: the indicator "prints" each ticket to the PC (ticket mode)

The manual (§3.3.6) lets each port COM1/COM2/LPT use a **printer driver**. Set COM1 to a printer
driver and every weighing ticket the indicator prints is also sent as text, in the layout of §2.8:

```
DATE : 16/11/2026       TIME : 10h52
WEIGHING No : 000004-IO
DSD No       : 013883
VEHICLE No   :3-98673
GROSS :             38760kg
TARE :              15240kg
NET :               23520kg
```

The bridge reads weighing number, **DSD number** (the legal alibi-memory number), vehicle, dates and
gross/tare/net, and sends the ticket to Odoo (*Weighbridge ▸ Indicator Tickets*). The operator keeps
weighing on the indicator exactly as today (F1 entry, F2 exit). In Odoo, on the weighbridge ticket,
**Fill from Indicator Ticket** takes the indicator ticket of the same truck plate (spaces/dashes
ignored, last 2 days) and records gross, tare, net and DSD as weights *From Scale*. The indicator ticket can also be chosen by hand.

Why this mode: it uses only what the manual documents, needs no Master-K protocol licence, keeps
the operator's routine, and Odoo gets the same figures and DSD number as the paper slip.

### Optional: live weight (weight mode)

Driver **1 = Weight repeater** streams the live weight (for a remote display). Its frame format
is not in the manual; run `--sniff` to see it, then `mode = weight` and tune `weight_regex` /
`motion_marker`. Drivers 2 (FDE Computer) and 4 (ERIC protocol) are Master-K PC protocols: ask
Master-K for their documentation if ever needed.

## Step 1 — Settings on the indicator (F6 Management menu ▸ F6 = PARAMETER COM1/COM2/LPT)

The management menu may be protected by a code; the communication settings are not metrological
(the weighing calibration is not touched). For **COM1**:

| Parameter | Value | Meaning (manual §3.3.6) |
|---|---|---|
| DRIVER | **8** | ILA410/ILA800 printer, 80 columns (use **7** = IBA40, 40 columns, if lines arrive cut) |
| TYPE | **0** | RS-232 without DTR test (so the PC needs no handshake wiring) |
| SPEED | **9** | 9600 bauds |
| BITS | **8** | 8 data bits |
| PARITY | **0** | none |
| STOP | **1** | 1 stop bit |

Leave **LPT** as it is (the slip printer). After saving, do one test weighing and check both that
the paper slip still prints and that text arrives on the PC (Step 3). If the indicator prints to
only one printer port, keep paper on LPT and ask Master-K how to send a duplicate to COM1, or
use F7 ▸ DSD ▸ F3 transmission (below) as a daily import.

Also check *F6 Management ▸ operation mode* (manual §3.3.2) that tickets are printed at the exit
weighing ("1: weigh in / weigh out validated and output ticket" or "2: … input and output ticket").

## Step 2 — Cable and PC

- COM1 is **RS-232**, **10 m maximum** (COM2 is a current loop for long distances). Check whether
  its connector is a DB9 or screw terminals before buying the cable; full shopping list and network
  options in [WEIGHBRIDGE_PC_SETUP.md](WEIGHBRIDGE_PC_SETUP.md).
- PC with a COM port, or a **USB-to-RS232 adapter** (FTDI chip recommended), and a **null-modem**
  DB9 cable (TX/RX crossed). If nothing arrives, try a straight DB9 cable.
- The indicator's USB port only offers the FDE/ERIC protocols, not the printer text — use COM1.
- The PC needs network access to the Odoo server (port 8069). A keyboard and screen are only needed
  for the set-up; afterwards it can run without anyone logged in.

## Step 3 — Install the bridge on the PC (Windows)

1. Install Python 3 (python.org, tick "Add to PATH"), then `pip install pyserial`.
2. Copy `ddfsc_weighbridge/tools/` to `C:\DDFSC\scale\`.
3. Odoo account: user **weighbridge.device** exists in `ddfsc` (group *Weighbridge ▸ Scale Device*
   only). Its API key is in `Claude outputs/scale_bridge.ini` (valid 89 days; Odoo limits API keys
   of normal users to 90 days — create a new one before it expires: log in as that user ▸ My
   Profile ▸ Account Security ▸ New API Key).
4. Copy `scale_bridge.ini.example` to `scale_bridge.ini`: `url` = the Odoo server address on the
   LAN, `api_key`, `port` (find it with `python scale_bridge.py --list-ports`), `mode = ticket`.
5. **Sniff first**: `python scale_bridge.py --config scale_bridge.ini --sniff`, then do a test
   weighing (or reprint a ticket). The printed lines must appear. Send the output to the developer
   if the labels differ from the manual — tuning is a one-line change.
6. Run: `python scale_bridge.py --config scale_bridge.ini`. Each ticket is logged
   ("Ticket 000004 DSD 013883 3-98673: gross … tare … net …") and appears in Odoo under
   *Weighbridge ▸ Indicator Tickets*.
7. Auto-start: Task Scheduler ▸ Create Task ▸ trigger *At startup*, action
   `pythonw.exe C:\DDFSC\scale\scale_bridge.py --config C:\DDFSC\scale\scale_bridge.ini`,
   "Run whether user is logged on or not", restart every minute on failure. Set `log_file` in the ini.

The bridge reconnects by itself after cable, indicator or network interruptions. A ticket that
cannot be sent after 3 attempts is written to the log with its full text — keep the paper slip.

## Using it in Odoo

1. Weighbridge ▸ Tickets ▸ New: operation, plate (as typed on the indicator), product, PO/receipt.
2. The truck is weighed on the indicator (entry, then exit). When the exit ticket prints, it arrives
   in Odoo.
3. On the Odoo ticket: **Fill from Indicator Ticket** → gross, tare, net and DSD are filled,
   both weighings marked *From Scale*. **Complete Ticket**.
4. Typed weights remain possible (today's way of working): type the weights and the **DSD No.** printed on
   the slip; the DSD number is required for typed weights, no photo is needed. They are marked *Typed*.

## Historical data: DSD transmission (manual §2.6.3)

F7 (DSD) ▸ F3 sends the alibi memory between two dates to COM1 at 9600 8N1. Capture it with
`python scale_bridge.py --config scale_bridge.ini --sniff > dsd_export.txt` while the indicator
transmits — useful to reconcile past weighings.

## Demo without hardware

`python scale_bridge.py --config scale_bridge.ini --simulate` (with `mode = ticket`) sends a printed
ticket for truck 3-98673 every 15 seconds; create an Odoo ticket for plate 3-98673 and press
*Fill from Indicator Ticket*. With `mode = weight`, `--simulate` streams a live weight instead.

## Troubleshooting

| Symptom | Check |
|---|---|
| Nothing in `--sniff` | COM1 DRIVER = 8 and saved? 9600-8-N-1 both sides? Null-modem vs straight cable; COM port number. |
| Garbled characters | Speed/bits/parity differ between indicator and ini. |
| Lines cut at 40 characters | Use DRIVER 8 (80 columns). |
| "No indicator ticket … for vehicle" | Plate typed differently on the indicator and in Odoo; pick the ticket by hand in *Indicator Ticket*. |
| "Odoo refused the login" | API key expired or wrong; device user archived. |
| Ticket on paper but not in Odoo | Look in the bridge log: it holds the full ticket text when Odoo was unreachable. |
