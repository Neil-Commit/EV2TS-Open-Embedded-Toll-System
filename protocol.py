"""
Micro-protocol parser/formatter
Upstream   (ESP32 -> Gateway):  @SCAN,<GATE_TYPE>,<LANE_ID>,<HEX_UID>
Downstream (Gateway -> ESP32):  @ACTION,<LANE_ID>,<STATUS>,<REASON>
"""
class ProtocolError(ValueError):
    pass
def parse_scan_line(line: str) -> dict:
    line = line.strip()
    if not line.startswith("@SCAN,"):
        raise ProtocolError(f"Not a @SCAN packet: {line!r}")
    parts = line.split(",")
    if len(parts) != 4:
        raise ProtocolError(f"Malformed @SCAN packet (expected 4 fields): {line!r}")
    _, gate_type, lane_id, hex_uid = parts
    if gate_type.upper() not in ("ENTRY", "EXIT"):
        raise ProtocolError(f"Unknown GATE_TYPE in @SCAN packet: {line!r}")
    return {"gate_type": gate_type.upper(), "lane_id": lane_id, "rfid_uid": hex_uid.upper()}
def format_action_line(lane_id: str, status: str, reason: str) -> str:
    return f"@ACTION,{lane_id},{status},{reason}"
def parse_recharge_line(line: str) -> dict:
    line = line.strip()
    if not line.startswith("RECHARGE,"):
        raise ProtocolError(f"Not a RECHARGE command: {line!r}")
    parts = line.split(",")
    if len(parts) != 3:
        raise ProtocolError(f"Malformed RECHARGE command: {line!r}")
    _, vehicle_number, amount = parts
    try:
        return {"vehicle_number": int(vehicle_number), "amount": int(amount)}
    except ValueError as e:
        raise ProtocolError(f"Non-numeric RECHARGE fields: {line!r}") from e
