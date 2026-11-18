# Weighbridge PC — Set-up, Network and Cables

This guide covers the computer at the weighbridge: what to buy, how to cable it, how to reach Odoo
and the internet, and (optionally) how to connect the Master-K IDé 500 indicator so its tickets
arrive in Odoo by themselves.

The guide has two levels. **Level 1 is enough to start**; level 2 can be added later without
changing anything in level 1.

| Level | What the operator does | What is needed |
|---|---|---|
| **1. Manual entry (today's way of working)** | Weighs on the indicator as usual, then types gross, tare and the **DSD No.** from the paper slip into the Odoo ticket. | A PC with a browser and a network connection to Odoo. **No cable to the indicator.** |
| **2. Automatic capture (optional)** | Weighs on the indicator as usual; in Odoo presses **Fill from Indicator Ticket**. | Level 1 + one serial cable from the indicator's COM1 to the PC + the small *scale bridge* program. |

Technical details of level 2 (all bridge settings, troubleshooting) are in
[SCALE_INTEGRATION.md](SCALE_INTEGRATION.md).

---

## 1. What the indicator offers (from the IDé 500 manuals)

| Port on the indicator | What it is | Use for us |
|---|---|---|
| **COM1** | RS-232 (or RS-485 2-wire), **10 m maximum** | **The PC connection** (level 2). Set to a printer driver, it sends each ticket as text. |
| COM2 | Passive current loop; RS-232 / RS-485 / **Ethernet as a paid option card** | Long distances. Only if the PC must be far away (see §5.3). |
| LPT | Parallel printer port, 3 m max | The slip printer. **Leave it as it is.** |
| USB (slave) | Only Master-K PC protocols (FDE / ERIC) | **Not usable** for tickets without Master-K's software. |
| Power | 230 V 50/60 Hz **+ earth**, 15–25 VA | Same circuit as the PC (see §4). |

> The indicator is a **legal-for-trade (metrology) instrument**. Do not open its sealed housing or
> change weighing/calibration settings. If COM1's connector is inside the housing, or the
> management menu asks for a code, **ask the Master-K technician** to fit the cable and set the
> port. Changing only the communication port does not touch the calibration.

---

## 2. Shopping list

### Level 1 — manual entry

| # | Item | Notes |
|---|---|---|
| 1 | **Desktop PC** (or mini PC / laptop) | Windows 10/11, 8 GB RAM, SSD. Any office PC that runs Chrome or Edge is fine. |
| 2 | Monitor, keyboard, mouse | A 19–22" monitor is enough. |
| 3 | **UPS** (650–1000 VA, line-interactive) | Power cuts are common; keeps the PC and the indicator alive long enough to finish a weighing. |
| 4 | **Surge-protected power strip** with earth | Weighbridges are big metal structures outdoors and attract surges. |
| 5 | **Network connection** — one of the options in §5 | Ethernet cable, Wi-Fi bridge, or 4G router. |
| 6 | Optional: A4 or receipt printer | Only if you want to print Odoo documents at the weighbridge. The indicator keeps its own slip printer. |

### Level 2 — add for automatic capture

| # | Item | Notes |
|---|---|---|
| 7 | **USB-to-RS232 adapter, FTDI chip, ideally *isolated*** | Most PCs have no COM port. "Isolated" protects the PC from earth differences between the weighbridge and the building. Avoid cheap no-name (Prolific/CH340) adapters — they drop data. |
| 8 | **Null-modem serial cable, DB9 female–female, 1.8–3 m** | TX and RX are crossed. Total length to the indicator **≤ 10 m**. |
| 9 | Straight-through DB9 cable (spare) + DB9 **gender changer** | If nothing arrives with the null-modem cable, the straight one is the other possibility; the gender changer fixes a male/female mismatch. |
| 10 | Optional: **serial-to-Ethernet converter** (e.g. Moxa NPort 5110, USR-TCP232-302) | Only if the PC is more than 10 m from the indicator (§5.3). |

**Before buying items 8–9:** look at COM1 on the indicator (or ask Master-K) to see whether it is a
9-pin D connector (male or female) or screw terminals. If it is screw terminals, the technician
makes the cable: only **3 wires** are needed — **TX, RX and GND** (TYPE 0 = no DTR handshake).

---

## 3. Placing the PC

- Inside the weighbridge cabin, **next to the indicator** (within 10 m of COM1 for level 2).
- Away from water, dust and direct sun; on a desk, not on the floor.
- The operator should see the indicator display and the PC screen from the same seat.

---

## 4. Power

1. Plug the **UPS** into an **earthed** 230 V socket — the same circuit as the indicator if possible.
2. PC, monitor and (optionally) the indicator go on the UPS outlets; the printer on a surge strip
   (printers draw too much for a small UPS).
3. If the indicator and the PC are on different circuits, use the **isolated** USB-RS232 adapter
   (item 7) for level 2.
4. Set the PC BIOS to **"power on after power loss"** so it restarts by itself after a long cut.

---

## 5. Network: reaching Odoo and the internet

First find out where Odoo runs. Open Odoo from an office PC and look at the address bar:

- **An internet address** (for example `https://erp.yourcompany.com`): the weighbridge PC only needs
  **internet access**.
- **A local address** (for example `http://192.168.1.10:8069`): the weighbridge PC must be on the
  **factory network (LAN)**. Internet then comes from the same LAN.

Then pick the connection that fits the distance from the office/server room to the weighbridge:

| Distance from the nearest network switch | Recommended connection |
|---|---|
| **Up to 90 m** | **Outdoor Cat6 Ethernet cable** (UV-resistant, in a conduit or buried pipe), RJ45 at both ends. Most reliable. |
| **90 m – 2 km, line of sight** | **Point-to-point Wi-Fi bridge** (a pair of outdoor 5 GHz antennas, e.g. Ubiquiti NanoStation/LiteBeam, TP-Link CPE). One at the office, one at the cabin; a short Ethernet cable from the cabin antenna to the PC. |
| **Longer, or through buildings** | **Fibre optic** with a media converter at each end (ask the IT colleague), or a 4G router (below). |
| **Odoo is on the internet and there is no LAN at the weighbridge** | **4G/LTE router with a SIM card** (Ethio Telecom / Safaricom data), Ethernet from the router to the PC. |

Avoid ordinary indoor Wi-Fi from a distant building: it drops in and out, and the operator loses the
page in the middle of a ticket.

### 5.1 Cabling at the cabin

```
 [Office switch] ──Cat6 outdoor / Wi-Fi bridge / fibre──► [small 5-port switch in the cabin]
                                                              ├──Cat6 patch──► Weighbridge PC
                                                              └──(spare)──► serial-to-Ethernet converter (§5.3)
```

A small 5-port switch in the cabin (also on the UPS) leaves room for a second device later.

### 5.2 Check the connection

On the weighbridge PC:

1. Open Chrome/Edge and type the Odoo address. The Odoo login page must appear.
2. If Odoo is on the LAN, also check internet (open any website) — needed for Windows updates and
   for remote help (AnyDesk).
3. Write the Odoo address on a label stuck on the monitor.

### 5.3 If the PC must be more than 10 m from the indicator (level 2 only)

RS-232 is limited to 10 m. Instead of a long serial cable:

- put a **serial-to-Ethernet converter** next to the indicator, connected to COM1 with a short
  null-modem cable, and to the cabin switch with Cat6; give it a fixed IP address;
- in the bridge settings use `connection = tcp`, `tcp_host = <converter IP>`, `tcp_port = 4001`;
- the bridge can then run on any PC on the network — or on the Odoo server itself.

Master-K also sells an **Ethernet option card for COM2**; ask them for a quote if you prefer that.

---

## 6. Set up the PC (level 1)

1. Install Windows updates and **Chrome** (or use Edge).
2. Create a Windows user for the operators (not an administrator account).
3. Open the Odoo address, log in once as the weighbridge operator, and **pin the tab** /
   create a desktop shortcut to *Weighbridge ▸ Tickets*.
4. Install **AnyDesk** so IT can help remotely.
5. Set the screen not to lock during working hours (Settings ▸ Power).
6. Each operator logs in to Odoo with **their own user** — tickets record who weighed.

### Daily use (level 1)

1. *Weighbridge ▸ Tickets ▸ New*: operation (purchase receipt / sale delivery), truck plate, product,
   purchase order / receipt.
2. Weigh the truck on the indicator as today (F1 entry, F2 exit) — the slip prints.
3. In Odoo type **Gross**, **Tare** and the **DSD No.** printed on the slip (no photo needed).
   Odoo calculates the net and marks the weights *Typed*.
4. **Complete Ticket**. Keep the paper slip with the delivery documents.

---

## 7. Connect the indicator (level 2, optional)

Do these in order; each step can be checked before the next.

1. **Cable** — with the indicator **switched off**: COM1 ─ null-modem cable ─ USB-RS232 adapter ─ PC USB port.
   Tighten the DB9 screws; tie the cable so nobody pulls it.
2. **Adapter driver** — Windows usually installs the FTDI driver by itself. In *Device Manager ▸
   Ports (COM & LPT)* note the number, e.g. **COM3**.
3. **Indicator settings** (F6 Management ▸ F6 = PARAMETER COM1/COM2/LPT, by the Master-K technician
   if a code is asked): COM1 **DRIVER 8** (80-column printer), **TYPE 0**, **SPEED 9** (9600),
   **BITS 8**, **PARITY 0**, **STOP 1**. Leave LPT unchanged.
4. **Install the bridge** — Python 3 (tick *Add to PATH*), `pip install pyserial`, copy
   `ddfsc_weighbridge/tools/` to `C:\DDFSC\scale\`, fill `scale_bridge.ini` (Odoo address, API key of
   the `weighbridge.device` user, `port = COM3`, `mode = ticket`).
5. **Sniff test** — `python scale_bridge.py --config scale_bridge.ini --sniff`, then do a test
   weighing: the ticket lines (WEIGHING No, DSD No, VEHICLE No, GROSS/TARE/NET) must appear.
   - Nothing at all → swap to the straight cable, check the COM number and DRIVER 8 saved.
   - Strange characters → speed/parity differ; 9600-8-N-1 on both sides.
6. **Run** — `python scale_bridge.py --config scale_bridge.ini`; the ticket appears in Odoo under
   *Weighbridge ▸ Indicator Tickets*.
7. **Auto-start** — Task Scheduler ▸ *At startup* ▸ `pythonw.exe C:\DDFSC\scale\scale_bridge.py
   --config C:\DDFSC\scale\scale_bridge.ini`, "run whether user is logged on or not", restart on failure.
8. **Renew the API key every 89 days** (Odoo limits keys of normal users to 90 days) — put a
   reminder in the calendar.

Daily use then changes only at step 3 of §6: instead of typing, press **Fill from Indicator Ticket**.
Typing stays possible as a fallback when the cable or bridge is down.

---

## 8. Checklist before go-live

- [ ] PC on UPS; UPS on an earthed socket; BIOS "power on after power loss" set
- [ ] Network: Odoo login page opens on the weighbridge PC; internet works
- [ ] Odoo address on a label; desktop shortcut to Weighbridge ▸ Tickets
- [ ] Each operator has their own Odoo user and has done one test ticket
- [ ] AnyDesk installed and its ID given to IT
- [ ] *(level 2)* COM1 set to DRIVER 8, 9600-8-N-1; paper slip still prints
- [ ] *(level 2)* `--sniff` shows the ticket text; a test ticket reaches Odoo
- [ ] *(level 2)* Bridge auto-starts after a PC restart; API key renewal date in the calendar

## 9. Who to call

| Problem | Who |
|---|---|
| Indicator settings, sealed housing, COM1 connector, Ethernet option card | **Master-K / Arpège** technician |
| Network cable, Wi-Fi bridge, 4G router, PC | Factory IT |
| Odoo users, API key, bridge program | Odoo developer |
