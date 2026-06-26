"""
frfr hardware integration.

Bridges TWO real serial ports the ESP32 WROOM 32U Entrance node and
the ESP32 30-Pin Exit node sa TollwayEngine /TollwayDB.
"""

import argparse
import queue
import sys
import threading
import time

import serial
import serial.tools.list_ports

from database import TollwayDB
from engine import TollwayEngine
from protocol import parse_scan_line, parse_recharge_line, format_action_line, ProtocolError


class SerialNode:

    def __init__(self, name, port, baud, incoming_queue):
        self.name = name
        self.port_name = port
        self.baud = baud
        self.incoming_queue = incoming_queue
        self.ser = None
        self._stop = threading.Event()
        self._thread = None

    def open(self):
        self.ser = serial.Serial(self.port_name, self.baud, timeout=1)
        time.sleep(2)  # let the ESP32 finish its reset-on-connect, same idea as html.md's boot delay
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        print(f"[BRIDGE] {self.name} node online on {self.port_name} @ {self.baud} baud")

    def _read_loop(self):
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.ser.read(self.ser.in_waiting or 1)
            except (serial.SerialException, OSError) as e:
                print(f"[BRIDGE] {self.name} read error: {e}")
                break
            if chunk:
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode(errors="replace").strip("\r\n ")
                    if text:
                        self.incoming_queue.put((self.name, text))

    def send(self, line: str):
        if self.ser and self.ser.is_open:
            self.ser.write((line + "\n").encode())

    def close(self):
        self._stop.set()
        if self.ser and self.ser.is_open:
            self.ser.close()


def list_ports():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports detected.")
        return
    print("Available serial ports:")
    for p in ports:
        print(f"  {p.device}  —  {p.description}")


def console_input_loop(cmd_queue):
    """RECHARGE,<vehicle>,<delta> in dashboard."""
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip():
            cmd_queue.put(("CONSOLE", line.strip()))


def handle_line(source, line, engine: TollwayEngine, db: TollwayDB, nodes: dict):
    print(f">> [{source}] {line}")

    if line.startswith("@SCAN,"):
        try:
            scan = parse_scan_line(line)
        except ProtocolError as e:
            print(f"   << @ERR,{e}")
            return
        result = engine.process_scan(scan["gate_type"], scan["lane_id"], scan["rfid_uid"])
        action = format_action_line(result["lane_id"], result["status"], result["reason"])
        print(f"   << {action}   (vehicle={result['vehicle_number']}, "
              f"balance={result['balance']}, is_inside={result['is_inside']})")
        # Route the @ACTION back down to whichever physical node the scan came from
        if source in nodes:
            nodes[source].send(action)

    elif line.startswith("RECHARGE,"):
        try:
            rc = parse_recharge_line(line)
        except ProtocolError as e:
            print(f"   << @ERR,{e}")
            return
        result = engine.process_recharge(rc["vehicle_number"], rc["amount"])
        if result["ok"]:
            print(f"   << @REC,{result['vehicle_number']},{rc['amount']},{result['balance']}")
        else:
            print(f"   << @ERR,{result['reason']}")

    elif line.strip().upper() == "DUMP":
        for row in db.dump_all():
            print("   ", dict(row))

    else:
        # Plain boot/debug text from a board (e.g. "[ENTRANCE NODE] Ready.") -- just echo it
        pass


def main():
    parser = argparse.ArgumentParser(description="Real hardware bridge for the Tollway gateway")
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument("--entry-port", help="Serial port for the ESP32 Entrance node")
    parser.add_argument("--exit-port", help="Serial port for the ESP32 Exit node")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--reset-db", action="store_true", help="Wipe tollway.db before starting")
    args = parser.parse_args()

    if args.list_ports:
        list_ports()
        return

    if not args.entry_port and not args.exit_port:
        print("Provide at least one of --entry-port / --exit-port (or run --list-ports first).")
        sys.exit(1)

    db = TollwayDB(reset=args.reset_db)
    engine = TollwayEngine(db)

    incoming = queue.Queue()
    nodes = {}

    if args.entry_port:
        nodes["ENTRY"] = SerialNode("ENTRY", args.entry_port, args.baud, incoming)
        nodes["ENTRY"].open()
    if args.exit_port:
        nodes["EXIT"] = SerialNode("EXIT", args.exit_port, args.baud, incoming)
        nodes["EXIT"].open()

    threading.Thread(target=console_input_loop, args=(incoming,), daemon=True).start()

    print("\n[BRIDGE] Listening. Tap a card, or type RECHARGE,<vehicle>,<delta> / DUMP.\n")

    try:
        while True:
            source, line = incoming.get()
            handle_line(source, line, engine, db, nodes)
    except KeyboardInterrupt:
        print("\n[BRIDGE] Shutting down...")
    finally:
        for node in nodes.values():
            node.close()
        db.close()


if __name__ == "__main__":
    main()
