"""
Run it:
    pip install fastapi uvicorn
    python3 server.py --entry-port COM8 --exit-port COM9
    -> open http://localhost:8000/ in a browser
"""

import argparse
import asyncio
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from database import TollwayDB
from engine import TollwayEngine
from protocol import parse_scan_line, parse_recharge_line, format_action_line, ProtocolError
from serial_bridge import SerialNode
import queue

STATIC_DIR = Path(__file__).parent / "static"

db: TollwayDB = None
engine: TollwayEngine = None
main_loop: asyncio.AbstractEventLoop = None

incoming: "queue.Queue" = queue.Queue()
nodes: dict[str, SerialNode] = {}


class ConnectionManager:
    """Tracks every connected browser tab so results can be broadcast to all of them."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


def process_incoming_line(source: str, line: str):
    if line.startswith("@SCAN,"):
        try:
            scan = parse_scan_line(line)
        except ProtocolError as e:
            return {"type": "error", "message": str(e)}

        result = engine.process_scan(scan["gate_type"], scan["lane_id"], scan["rfid_uid"])

        if source in nodes:
            action = format_action_line(result["lane_id"], result["status"], result["reason"])
            nodes[source].send(action)

        return {"type": "scan_result", "rfid_uid": scan["rfid_uid"], **result}

    if line.startswith("RECHARGE,"):
        try:
            rc = parse_recharge_line(line)
        except ProtocolError as e:
            return {"type": "error", "message": str(e)}
        result = engine.process_recharge(rc["vehicle_number"], rc["amount"])
        if result["ok"]:
            return {"type": "recharge_result", "vehicle_number": result["vehicle_number"],
                     "delta": rc["amount"], "balance": result["balance"]}
        return {"type": "error", "message": result["reason"]}

    return None 


def queue_drain_worker():
    while True:
        source, line = incoming.get()
        try:
            result = process_incoming_line(source, line)
        except Exception as e:
            print(f"[SERVER] ERROR processing line from {source} ({line!r}): {e}")
            continue
        if result is not None and main_loop is not None:
            asyncio.run_coroutine_threadsafe(manager.broadcast(result), main_loop)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop, db, engine

    main_loop = asyncio.get_running_loop()

    reset_db = os.environ.get("TOLLWAY_RESET_DB") == "1"
    db = TollwayDB(reset=reset_db)
    engine = TollwayEngine(db)

    entry_port = os.environ.get("TOLLWAY_ENTRY_PORT")
    exit_port = os.environ.get("TOLLWAY_EXIT_PORT")
    baud = int(os.environ.get("TOLLWAY_BAUD", "115200"))

    if entry_port:
        nodes["ENTRY"] = SerialNode("ENTRY", entry_port, baud, incoming)
        nodes["ENTRY"].open()
    if exit_port:
        nodes["EXIT"] = SerialNode("EXIT", exit_port, baud, incoming)
        nodes["EXIT"].open()
    if os.environ.get("TOLLWAY_EXIT2_PORT"):
        nodes["EXIT2"] = SerialNode("EXIT2", os.environ["TOLLWAY_EXIT2_PORT"], baud, incoming)
        nodes["EXIT2"].open()

    if not nodes:
        print("[SERVER] No --entry-port / --exit-port given -- running with no hardware "
              "attached. The dashboard will load but nothing will ever scan.")

    if not (STATIC_DIR / "index.html").exists():
        print(f"[SERVER] WARNING: {STATIC_DIR / 'index.html'} not found. "
              "The dashboard page will return a 500 error until it's there.")
    if not (STATIC_DIR / "logo.png").exists():
        print(f"[SERVER] WARNING: {STATIC_DIR / 'logo.png'} not found. "
              "The dashboard will load but the logo image will be broken.")

    threading.Thread(target=queue_drain_worker, daemon=True).start()

    yield 

    for node in nodes.values():
        node.close()
    if db is not None:
        db.close()


app = FastAPI(title="Tollway Gateway", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse(
            "<h1>Setup issue</h1>"
            f"<p>Expected the dashboard file at <code>{html_path}</code>, "
            "but it isn't there.</p>"
            "<p>Make sure a <code>static</code> folder sits in the same "
            "directory as <code>server.py</code>, containing "
            "<code>index.html</code> and <code>logo.png</code>.</p>",
            status_code=500,
        )
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/accounts")
async def api_accounts():
    return {"accounts": [dict(row) for row in db.dump_all()]}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    await websocket.send_json({
        "type": "hydrate",
        "accounts": [dict(row) for row in db.dump_all()],
        "connected_nodes": list(nodes.keys()),  # e.g. ["ENTRY", "EXIT"]
    })

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "recharge":
                result = engine.process_recharge(data["vehicle_number"], data["delta"])
                if result["ok"]:
                    await manager.broadcast({
                        "type": "recharge_result",
                        "vehicle_number": result["vehicle_number"],
                        "delta": data["delta"],
                        "balance": result["balance"],
                    })
                else:
                    await websocket.send_json({"type": "error", "message": result["reason"]})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tollway FastAPI gateway server")
    parser.add_argument("--entry-port",  help="Serial port — Entrance node (Balintawak + Mindanao Ave)")
    parser.add_argument("--exit-port",   help="Serial port — Exit Node 1 (Valenzuela + Meycauayan)")
    parser.add_argument("--exit2-port",  help="Serial port — Exit Node 2 (Marilao + Bocaue)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reset-db", action="store_true", help="Wipe tollway.db before starting")
    args = parser.parse_args()

    if args.entry_port:
        os.environ["TOLLWAY_ENTRY_PORT"] = args.entry_port
    if args.exit_port:
        os.environ["TOLLWAY_EXIT_PORT"] = args.exit_port
    if args.exit2_port:
        os.environ["TOLLWAY_EXIT2_PORT"] = args.exit2_port
    os.environ["TOLLWAY_BAUD"] = str(args.baud)
    if args.reset_db:
        os.environ["TOLLWAY_RESET_DB"] = "1"

    uvicorn.run(app, host=args.host, port=args.port)
