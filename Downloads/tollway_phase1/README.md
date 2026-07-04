# Ev2TS — Electroboom v2 Toll System

A Miniature Proof-of-Concept for Open-Toll RFID Expressway Management System built on PN532 sensors, ESP32 microcontrollers, a Python FastAPI gateway, and a real-time browser dashboard. Designed around the northbound segment of a Philippine expressway, from Balintawak to Bocaue.

> **Open-toll model:** also known as (open-road or cashless tolling) is a highway system where vehicles are tolled as they pass overhead gantries or sensors, rather than at physical toll plazas. Because there are no booths or barriers, drivers never have to stop or slow down, allowing traffic to flow continuously. This mirrors real-world RFID open-toll systems like SALIK and DARB.

---

## System Overview

```
[ PN532 RFID Sensors ]
        |  SPI
[ ESP32 Nodes ] ──── USB Serial ────> [ Python Gateway ] <──> [ SQLite DB ]
  (3 boards)         @SCAN / @ACTION    server.py / engine.py
                                               |
                                         WebSocket (JSON)
                                               |
                                     [ Web-based Dashboard ]
                                          index.html
```

Three ESP32 nodes each host two PN532 RFID readers. When a vehicle passes within range its RFID sticker at any interchange, the board sends a `@SCAN` packet to the Python gateway over USB serial. The gateway runs the business fare logic, updates the database, replies with `@ACTION`, and broadcasts the result to the interface.

---

## Interchange Layout

Single northbound carriageway. Physical order along the road (ingress and egress):

```
IN1              IN2                EX1              EX2            EX3          EX4
Balintawak  -->  Mindanao Ave  -->  Valenzuela  -->  Meycauayan --> Marilao  --> Bocaue
KM 12            KM 13.5            KM 15            KM 19          KM 23        KM 27
```

---

## Hardware

| Board | Role | Sensors |
|---|---|---|
| ESP32 WROOM 32U | Entrance Node | PN532 Lane 1 (Balintawak), PN532 Lane 2 (Mindanao Ave) |
| ESP32 DevKit V1 | Exit Node 1 | PN532 Lane 1 (Valenzuela), PN532 Lane 2 (Meycauayan) |
| ESP32 DevKit V1 | Exit Node 2 | PN532 Lane 3 (Marilao), PN532 Lane 4 (Bocaue) |

All PN532 modules must have DIP switches set to **SPI mode (I1=0, I2=1)** and be powered from an external **5V** supply with a shared ground.
*Additionally, you may use any ESP32 board, one mentioned was the one used in the original project.*

---

## Wiring

Each PN532 gets its own fully independent set of pins. Nothing is shared between Lane 1 and Lane 2 on any board. The same pin numbers are reused across all three boards.
*Independent pins were chosen to simplify the connection on our end, even though sharing the SCK, MISO, and MOSI is perfectly acceptable.*

| Signal | Lane 1 | Lane 2 |
|---|---|---|
| SCK | GPIO 18 | GPIO 14 |
| MISO | GPIO 19 | GPIO 27 |
| MOSI | GPIO 23 | GPIO 26 |
| CS / SS | GPIO 5 | GPIO 25 |
| RST | GPIO 4 | GPIO 33 |
| Power | 5V external | 5V external |
| Ground | GND (common) | GND (common) |

This table applies to all three boards. On Exit Node 2, Lane 1 firmware is labelled Lane 3 (Marilao) and Lane 2 is labelled Lane 4 (Bocaue) | same physical pins, different `LANE_ID` values in the firmware.

---

## Fare Matrix

Fares are determined at exit by the `(entry_lane, exit_lane)` pair. The system stamps which entry interchange a vehicle used on the way in, then prices accordingly on the way out.

| Entry | Exit | Distance | Toll |
|---|---|---|---|
| Balintawak (KM 12) | Valenzuela (KM 15) | 3.0 km | ₱50.50 |
| Balintawak (KM 12) | Meycauayan (KM 19) | 7.0 km | ₱64.50 |
| Balintawak (KM 12) | Marilao (KM 23) | 11.0 km | ₱78.50 |
| Balintawak (KM 12) | Bocaue (KM 27) | 15.0 km | ₱92.50 |
| Mindanao Ave (KM 13.5) | Valenzuela (KM 15) | 1.5 km | ₱45.25 |
| Mindanao Ave (KM 13.5) | Meycauayan (KM 19) | 5.5 km | ₱59.25 |
| Mindanao Ave (KM 13.5) | Marilao (KM 23) | 9.5 km | ₱73.25 |
| Mindanao Ave (KM 13.5) | Bocaue (KM 27) | 13.5 km | ₱87.25 |

To update fares, edit `FARE_MATRIX` in `engine.py`. No other file needs to change.

---

## Repository Structure

```
ev2ts/
├── server.py               # FastAPI web server
├── engine.py               # Business rule logic and fare matrix
├── database.py             # SQLite schema and data access layer
├── protocol.py             # @SCAN / @ACTION packet parser and formatter
├── serial_bridge.py        # SerialNode class: USB serial <-> Queue bridge
│
├── static/
│   ├── index.html          # Browser dashboard (WebSocket client)
│   └── logo.png            # Ev2TS brand mark
│
└── firmware/
    ├── entrance_node_esp32/
    │   └── entrance_node_esp32.ino    # Balintawak + Mindanao Ave
    ├── exit_node_esp32/
    │   └── exit_node_esp32.ino        # Valenzuela + Meycauayan
    └── exit_node2_esp32/
        └── exit_node2_esp32.ino       # Marilao + Bocaue
```

---

## File Descriptions

### `server.py`
The FastAPI application that ties everything together. On startup it opens serial connections to all three ESP32 nodes via `SerialNode` and starts a background thread (`queue_drain_worker`) that reads incoming `@SCAN` lines, runs them through the engine, and broadcasts the JSON result to every connected browser via WebSocket. Serves the dashboard at `/` and exposes `/api/accounts` for manual re-syncs. The WebSocket endpoint at `/ws` also receives `RECHARGE` messages from the dashboard.

### `engine.py`
The business rule logic engine. Contains the `FARE_MATRIX`, the `INTERCHANGE_NAMES` map, and `TollwayEngine` with two public methods: `process_scan()` and `process_recharge()`.

`process_scan()` state machine:

`process_recharge()` applies a relative delta only — there is no set-balance-to-absolute-value operation anywhere in the codebase.

### `database.py`
Opens (or creates) `tollway.db` and defines two tables:

- `accounts` — one row per registered RFID card: `vehicle_number`, `rfid_uid`, `balance` (REAL), `is_inside`, `entry_lane`
- `transaction_history` — one row per completed exit transaction: vehicle, lane, fare charged, timestamp

Includes a migration that safely adds the `entry_lane` column to any database created before that feature existed, without touching existing data.

### `protocol.py`
Strict parser and formatter for the `@`-prefixed wire protocol. Plain human-readable boot text from the boards is not parsed — it is logged and skipped.

- Upstream (ESP32 → Gateway): `@SCAN,<GATE_TYPE>,<LANE_ID>,<HEX_UID>`
- Downstream (Gateway → ESP32): `@ACTION,<LANE_ID>,<STATUS>,<REASON>`
- Dashboard command: `RECHARGE,<vehicle_number>,<delta>`

### `serial_bridge.py`
Contains `SerialNode` — a class that opens one serial port, runs a background reader thread, and places every received line into a shared `Queue`. Also contains a standalone console entry point (an earlier version of the gateway useful for debugging without starting the full web server).

### `static/index.html`
The browser dashboard. Connects to the gateway via WebSocket on page load and stays connected, auto-reconnecting every 2 seconds if the socket closes. On connect, the server pushes a full database snapshot (hydration) so the page is never blank.

- **Announcement banner** — 3-second shoutouwt for every event: interchange name, vehicle number, GRANT/DENY, fare and balance
- **Bullet-bar log** — full event log where a 3px colored left bar indicates outcome (green = OK, amber = penalty, red = denied, blue = info). Text stays neutral gray throughout
- **Interchange status grid** — compact per-sensor rows with live dot indicators that flash on each tap then return to READY
- **Account table** — all registered vehicles with balance (negative shown in red), on-highway status, and a SET button that computes the relative delta client-side

### Firmware files

All three `.ino` files follow the same pattern:

1. Drive all CS pins HIGH before calling `begin()` on any reader (the critical fix for SPI bus-sharing)
2. Run `getFirmwareVersion()` as a self-test on each reader — prints `[OK]` or `[ERROR]` on the serial monitor
3. Poll each reader in the main loop with a 2000ms cooldown; on a successful read emit `@SCAN,...`
4. Parse any incoming `@ACTION,...` line and print what a barrier would physically do

Only the `LANE_ID`, `GATE_TYPE`, and pin `#define` values differ between the three files.

---

## Setup

### 1. Install Arduino libraries

In the Arduino IDE Library Manager, install:
- `Adafruit PN532` by Adafruit

In Board Manager, add this URL and install the `esp32` package by Espressif:
```
https://dl.espressif.com/dl/package_esp32_index.json
```

### 2. Flash each board

| Board | Sketch |
|---|---|
| ESP32 WROOM 32U | `firmware/entrance_node_esp32/entrance_node_esp32.ino` |
| ESP32 30-Pin (Exit 1) | `firmware/exit_node_esp32/exit_node_esp32.ino` |
| ESP32 30-Pin (Exit 2) | `firmware/exit_node2_esp32/exit_node2_esp32.ino` |

After flashing each board, open Serial Monitor at **115200 baud** and confirm two `[OK] PN532 ... found` lines appear. Close Serial Monitor before running the server — Windows allows only one program to hold a COM port at a time.

### 3. Install Python dependencies

```bash
pip install fastapi uvicorn pyserial websockets
```

### 4. Find your COM ports

```bash
python server.py --list-ports
```

Unplug one board at a time and re-run to confirm which COM number belongs to which board.

### 5. Run the gateway

```bash
python server.py --entry-port COM8 --exit-port COM9 --exit2-port COM10
```

Replace `COM8`, `COM9`, `COM10` with your actual port numbers. On Linux/Mac idk I use windows onle HSAHAH.

Optional flags:

| Flag | Default | Description |
|---|---|---|
| `--reset-db` | off | Wipe `tollway.db` and start fresh |
| `--baud` | 115200 | Serial baud rate |
| `--port` | 8000 | HTTP port for the dashboard |
| `--host` | 0.0.0.0 | Bind address |

### 6. Open the dashboard

Open `http://localhost:8000/` in any browser on the same machine. STATUS should flip to **ONLINE** and the sensor dots go green for each connected node.

---

## License

In compliance with the requirements for the CPE0035L Embedded Systems Laboratory final project. |  Group 6  Banquil, Layco, Lista, Melo, Mendoza 
