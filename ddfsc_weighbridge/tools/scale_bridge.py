#!/usr/bin/env python3
"""DDFSC scale bridge: weighbridge indicator -> Odoo.

Runs headless (no screen needed) on a PC next to the weighbridge indicator
(Master-K IDé 500), or anywhere on the network when a serial-to-Ethernet
converter sits next to the indicator. Two modes:

* ticket (recommended for the IDé 500): the indicator's COM1 is set to a
  printer driver, so every weighing ticket it prints is also sent as text.
  The bridge reads WEIGHING No, DSD No, VEHICLE No, dates and GROSS / TARE /
  NET and sends the ticket to Odoo (``push_indicator_ticket``). The operator
  weighs on the indicator exactly as before; Odoo fills the weighbridge
  ticket from it.
* weight: the port is set to "weight repeater" and streams the live weight
  (``push_reading``); operators press "Capture … from Scale".

Usage
  python scale_bridge.py --config scale_bridge.ini            # run
  python scale_bridge.py --config scale_bridge.ini --sniff    # print raw frames only (set-up)
  python scale_bridge.py --config scale_bridge.ini --simulate # fake truck weights (demo, no hardware)
  python scale_bridge.py --list-ports                         # show COM ports on this PC

Only the Python standard library is needed, plus ``pyserial`` for serial/USB
(``pip install pyserial``).
"""

import argparse
import configparser
import json
import logging
import random
import re
import socket
import sys
import time
import urllib.request

LOG = logging.getLogger("scale_bridge")

DEFAULTS = {
    "odoo": {
        "url": "http://localhost:8069",
        "database": "ddfsc",
        "login": "weighbridge.device",
        "api_key": "",
        "scale_code": "WB1",
    },
    "indicator": {
        # ticket | weight
        "mode": "ticket",
        # Seconds without new text that close a ticket (when no NET line ends it).
        "ticket_idle_seconds": "3",
        # serial | tcp
        "connection": "serial",
        "port": "COM1",
        "baudrate": "9600",
        "bytesize": "8",
        "parity": "N",
        "stopbits": "1",
        "tcp_host": "192.168.1.50",
        "tcp_port": "4001",
        # Frames end with CR/LF on most indicators; ETX (\x03) is also accepted.
        "frame_end": "\\r\\n",
        # The weight is the last signed number in the frame unless weight_regex is set.
        "weight_regex": "",
        # Text that marks a moving (unstable) weight in the frame, e.g. "M" or "US". Empty: decide by repetition.
        "motion_marker": "",
        # Readings must repeat this many times (same value) to count as stable when no marker exists.
        "stable_repeats": "3",
        "dsd_regex": "DSD\\s*[:#]?\\s*(\\d+)",
        # Some set-ups answer only when asked: a command sent every poll_interval seconds (e.g. "\\x05" or "P\\r\\n").
        "poll_command": "",
        "poll_interval": "1.0",
        # Multiply the parsed number (e.g. 10 when the indicator sends tens of kg).
        "scale_factor": "1",
    },
    "bridge": {
        # Send at most this often while the weight does not change (keeps the scale "online" in Odoo).
        "heartbeat_seconds": "2",
        "log_file": "",
    },
}


def unescape(text):
    return text.encode("latin-1").decode("unicode_escape") if text else ""


class Odoo:
    """Minimal JSON-RPC client (no extra libraries)."""

    def __init__(self, cfg):
        self.url = cfg["url"].rstrip("/") + "/jsonrpc"
        self.db = cfg["database"]
        self.login = cfg["login"]
        self.key = cfg["api_key"]
        self.code = cfg["scale_code"]
        self.uid = None

    def _call(self, service, method, *args):
        payload = json.dumps({"jsonrpc": "2.0", "method": "call",
                              "params": {"service": service, "method": method, "args": args}}).encode()
        request = urllib.request.Request(self.url, payload, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            answer = json.loads(response.read().decode())
        if answer.get("error"):
            data = answer["error"].get("data", {})
            raise RuntimeError(data.get("message") or answer["error"].get("message"))
        return answer["result"]

    def push_ticket(self, ticket):
        self._login()
        return self._call("object", "execute_kw", self.db, self.uid, self.key,
                          "ddfsc.weighbridge.scale", "push_indicator_ticket", [self.code, ticket])

    def _login(self):
        if not self.uid:
            self.uid = self._call("common", "authenticate", self.db, self.login, self.key, {})
            if not self.uid:
                raise RuntimeError("Odoo refused the login %s (check login and API key)" % self.login)

    def push(self, weight, stable, raw, dsd):
        if not self.uid:
            self.uid = self._call("common", "authenticate", self.db, self.login, self.key, {})
            if not self.uid:
                raise RuntimeError("Odoo refused the login %s (check login and API key)" % self.login)
        return self._call("object", "execute_kw", self.db, self.uid, self.key,
                          "ddfsc.weighbridge.scale", "push_reading", [self.code, weight],
                          {"stable": stable, "raw": raw, "dsd": dsd})


class FrameParser:
    NUMBER = re.compile(r"([+-]?\s*\d+(?:[.,]\d+)?)")

    def __init__(self, cfg):
        self.weight_regex = re.compile(cfg["weight_regex"]) if cfg["weight_regex"] else None
        self.motion_marker = cfg["motion_marker"]
        self.dsd_regex = re.compile(cfg["dsd_regex"]) if cfg["dsd_regex"] else None
        self.repeats_needed = max(int(cfg["stable_repeats"]), 1)
        self.factor = float(cfg["scale_factor"])
        self.last_value = None
        self.repeats = 0

    def parse(self, frame):
        """Return (weight_kg, stable, dsd) or None when the frame has no weight."""
        text = frame.strip()
        if not text:
            return None
        if self.weight_regex:
            match = self.weight_regex.search(text)
            number = match.group(1) if match else None
        else:
            # Ignore the DSD counter when looking for the weight.
            searchable = self.dsd_regex.sub(" ", text) if self.dsd_regex else text
            numbers = self.NUMBER.findall(searchable)
            number = numbers[-1] if numbers else None
        if number is None:
            return None
        weight = float(number.replace(" ", "").replace(",", ".")) * self.factor
        if weight == self.last_value:
            self.repeats += 1
        else:
            self.last_value, self.repeats = weight, 1
        if self.motion_marker:
            stable = self.motion_marker not in text
        else:
            stable = self.repeats >= self.repeats_needed
        dsd = None
        if self.dsd_regex:
            match = self.dsd_regex.search(text)
            dsd = match.group(1) if match else None
        return weight, stable, dsd


class TicketParser:
    """Assemble the printed weighing ticket of the IDé 500 and read its fields.

    Layout from the IDé 500 weigh-bridge manual (section 2.8):
        DATE : 17/05/2005       TIME : 09h45
        WEIGHING No : 000004-IO
        DSD No       : 000001
        VEHICLE No   :1245ACC69
        GROSS :             46720kg
        TARE :              11660kg
        NET :               35060kg
    French labels (PESEE, No DSD, VEHICULE, BRUT) are accepted too.
    """

    WEIGHT = re.compile(r"^\s*(GROSS|BRUT|TARE|NET|P1|P2)\s*[:=]\s*([-+]?[\d\s.,]*\d)\s*(kg|t)\b", re.I)
    WEIGHING = re.compile(r"(?:WEIGHING|PES[EÉ]E)\s*N[o°]?\s*:\s*(\d+)\s*-?\s*([A-Z]{2})?", re.I)
    DSD = re.compile(r"(?:DSD\s*N[o°]?|N[o°]?\s*DSD)\s*[:=]\s*(\d+)", re.I)
    VEHICLE = re.compile(r"(?:VEHICLE|V[EÉ]HICULE)\s*N[o°]?\s*:\s*(.+)$", re.I)
    DATE = re.compile(r"DATE\s*:\s*(\d{2})/(\d{2})/(\d{4})\s+(?:TIME|HEURE)\s*:\s*(\d{1,2})\s*[hH:.]\s*(\d{2})", re.I)

    def __init__(self):
        self.reset()

    def reset(self):
        self.lines, self.values, self.dates = [], {}, []

    @staticmethod
    def _kg(number, unit):
        value = float(number.replace(" ", "").replace(",", "."))
        return value * 1000.0 if unit.lower() == "t" else value

    def feed(self, line):
        """Add one printed line; return a finished ticket dict or None."""
        line = line.replace("\x00", "").rstrip()
        if not line.strip():
            return None
        self.lines.append(line)
        match = self.WEIGHT.search(line)
        if match:
            key = {"BRUT": "gross", "GROSS": "gross", "TARE": "tare", "NET": "net",
                   "P1": "first_weight", "P2": "second_weight"}[match.group(1).upper()]
            self.values[key] = self._kg(match.group(2), match.group(3))
        for pattern, key in ((self.WEIGHING, "weighing_no"), (self.DSD, "dsd_no"), (self.VEHICLE, "vehicle")):
            found = pattern.search(line)
            if found:
                self.values[key] = found.group(1).strip()
                if key == "weighing_no" and found.group(2):
                    self.values["weighing_type"] = found.group(2).upper()
        found = self.DATE.search(line)
        if found:
            day, month, year, hour, minute = found.groups()
            self.dates.append("%s-%s-%s %02d:%s:00" % (year, month, day, int(hour), minute))
        if "net" in self.values and "gross" in self.values:
            return self.flush()
        return None

    def flush(self):
        """Close the current ticket (form feed, idle time or NET line)."""
        ticket = None
        if "gross" in self.values or "net" in self.values or "first_weight" in self.values:
            ticket = dict(self.values)
            if self.dates:
                ticket["weighing_date"] = self.dates[-1]
                if len(self.dates) > 1:
                    ticket["first_date"] = self.dates[0]
            ticket["raw"] = "\n".join(self.lines)[-2000:]
        self.reset()
        return ticket


def ticket_lines(source, idle_seconds):
    """Yield printed lines; yield None after ``idle_seconds`` of silence or a form feed."""
    buffer, last_data = "", time.time()
    while True:
        chunk = source.read(256)
        if not chunk:
            if time.time() - last_data >= idle_seconds:
                if buffer.strip():
                    yield buffer
                    buffer = ""
                yield None
                last_data = time.time()
            continue
        last_data = time.time()
        for char in chunk.decode("latin-1", "replace"):
            if char in "\r\n":
                if buffer:
                    yield buffer
                buffer = ""
            elif char == "\x0c":
                if buffer:
                    yield buffer
                buffer = ""
                yield None
            elif char >= " " or char == "\t":
                buffer += char


def simulated_ticket_lines():
    """A printed entry/exit ticket every 15 seconds (demo without hardware)."""
    number = 100
    while True:
        number += 1
        stamp = time.strftime("%d/%m/%Y       TIME : %Hh%M")
        for line in ("MASTER-K ARPEGE", "DATE : %s" % stamp, "WEIGHING No : %06d-IO" % number,
                     "DSD No       : %06d" % (13000 + number), "VEHICLE No   :3-98673",
                     "GROSS :             38760kg", "TARE :              15240kg",
                     "NET :               23520kg", "Signature :"):
            yield line
            time.sleep(0.2)
        yield None
        time.sleep(15)


def run_tickets(cfg, odoo, sniff=False, simulate=False):
    parser = TicketParser()
    idle = float(cfg["indicator"]["ticket_idle_seconds"])
    while True:
        source = None
        try:
            if simulate:
                lines = simulated_ticket_lines()
                LOG.info("Simulating printed weighbridge tickets (no hardware).")
            else:
                source = open_source(cfg["indicator"])
                lines = ticket_lines(source, idle)
                LOG.info("Connected to the indicator printer port (%s).", cfg["indicator"]["connection"])
            for line in lines:
                if sniff:
                    if line is not None:
                        print(repr(line))
                    continue
                ticket = parser.flush() if line is None else parser.feed(line)
                if not ticket:
                    continue
                for attempt in range(3):
                    try:
                        odoo.push_ticket(ticket)
                        LOG.info("Ticket %s DSD %s %s: gross %s tare %s net %s", ticket.get("weighing_no"),
                                 ticket.get("dsd_no"), ticket.get("vehicle"), ticket.get("gross"),
                                 ticket.get("tare"), ticket.get("net"))
                        break
                    except Exception as error:
                        odoo.uid = None
                        LOG.warning("Could not send ticket to Odoo (attempt %s): %s", attempt + 1, error)
                        time.sleep(5)
                else:
                    LOG.error("Ticket NOT sent, keep the paper slip: %s", ticket.get("raw"))
        except KeyboardInterrupt:
            return
        except Exception as error:
            LOG.error("Indicator connection lost: %s — retrying in 5 s", error)
            time.sleep(5)
        finally:
            if source:
                try:
                    source.close()
                except Exception:
                    pass


def open_source(cfg):
    if cfg["connection"] == "tcp":
        sock = socket.create_connection((cfg["tcp_host"], int(cfg["tcp_port"])), timeout=5)
        sock.settimeout(1.0)

        class TcpSource:
            def read(self, size=256):
                try:
                    return sock.recv(size)
                except socket.timeout:
                    return b""

            def write(self, data):
                sock.sendall(data)

            def close(self):
                sock.close()

        return TcpSource()
    try:
        import serial
    except ImportError:
        sys.exit("pyserial is missing: run  pip install pyserial")
    return serial.Serial(
        port=cfg["port"], baudrate=int(cfg["baudrate"]), bytesize=int(cfg["bytesize"]),
        parity=cfg["parity"].upper()[0], stopbits=float(cfg["stopbits"]), timeout=1.0)


def frames(source, cfg):
    """Yield text frames from the indicator, sending the poll command if configured."""
    ends = [unescape(cfg["frame_end"]).encode("latin-1"), b"\x03"]
    poll = unescape(cfg["poll_command"]).encode("latin-1")
    interval = float(cfg["poll_interval"])
    buffer, last_poll = b"", 0.0
    while True:
        if poll and time.time() - last_poll >= interval:
            source.write(poll)
            last_poll = time.time()
        chunk = source.read(256)
        if not chunk:
            continue
        buffer += chunk
        while True:
            cut = [(buffer.find(end), end) for end in ends if end and buffer.find(end) >= 0]
            if not cut:
                break
            index, end = min(cut)
            frame, buffer = buffer[:index], buffer[index + len(end):]
            yield frame.replace(b"\x02", b"").decode("latin-1", "replace")
        if len(buffer) > 4096:
            buffer = buffer[-256:]


def simulated_frames():
    """A truck drives on, settles, unloads, drives off — forever."""
    while True:
        for target in (0, 38760, 38760, 15240, 15240, 0):
            for _ in range(6):
                yield "ST,GS,%+08d kg" % (target + random.choice((0, 0, 0, 20, -20)))
                time.sleep(0.5)
            for _ in range(6):
                yield "ST,GS,%+08d kg" % target
                time.sleep(0.5)


def run(config_path, sniff=False, simulate=False):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_dict(DEFAULTS)
    if config_path:
        cfg.read(config_path, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        filename=cfg["bridge"]["log_file"] or None)
    odoo = Odoo(cfg["odoo"])
    if cfg["indicator"]["mode"] == "ticket":
        return run_tickets(cfg, odoo, sniff=sniff, simulate=simulate)
    parser = FrameParser(cfg["indicator"])
    heartbeat = float(cfg["bridge"]["heartbeat_seconds"])
    while True:
        source = None
        try:
            if simulate:
                stream = simulated_frames()
                LOG.info("Simulating a weighbridge (no hardware).")
            else:
                source = open_source(cfg["indicator"])
                stream = frames(source, cfg["indicator"])
                LOG.info("Connected to the indicator (%s).", cfg["indicator"]["connection"])
            last_sent = (None, None, 0.0)
            for frame in stream:
                if sniff:
                    print(repr(frame))
                    continue
                reading = parser.parse(frame)
                if not reading:
                    continue
                weight, stable, dsd = reading
                changed = (weight, stable) != last_sent[:2]
                if changed or time.time() - last_sent[2] >= heartbeat:
                    try:
                        odoo.push(weight, stable, frame[:120], dsd)
                        last_sent = (weight, stable, time.time())
                        if changed:
                            LOG.info("%s kg %s%s", weight, "stable" if stable else "moving",
                                     " DSD %s" % dsd if dsd else "")
                    except Exception as error:  # Odoo down or network: keep reading, retry later
                        odoo.uid = None
                        LOG.warning("Could not send to Odoo: %s", error)
                        time.sleep(2)
        except KeyboardInterrupt:
            return
        except Exception as error:
            LOG.error("Indicator connection lost: %s — retrying in 5 s", error)
            time.sleep(5)
        finally:
            if source:
                try:
                    source.close()
                except Exception:
                    pass


def main():
    arguments = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    arguments.add_argument("--config", help="INI file (see scale_bridge.ini.example)")
    arguments.add_argument("--sniff", action="store_true", help="print raw frames from the indicator and send nothing")
    arguments.add_argument("--simulate", action="store_true", help="send simulated truck weights (demo)")
    arguments.add_argument("--list-ports", action="store_true", help="list serial / USB COM ports")
    options = arguments.parse_args()
    if options.list_ports:
        from serial.tools import list_ports
        for port in list_ports.comports():
            print(port.device, "-", port.description)
        return
    run(options.config, sniff=options.sniff, simulate=options.simulate)


if __name__ == "__main__":
    main()
