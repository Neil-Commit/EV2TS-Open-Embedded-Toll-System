"""
backend processing engine.
"""

from database import TollwayDB, EXIT_COST

GRANT = "GRANT"
DENY = "DENY"
DEFAULT_FARE = EXIT_COST  # pag unknown

# -----------------------------------------------------------------------
# NLEX Northbound Expressway interchange name map
# Entry lanes:  "1" = Balintawak (KM 12),  "2" = Mindanao Ave (KM 13.5)
# Exit lanes:   "1" = Valenzuela (KM 15),  "2" = Meycauayan   (KM 19)
#               "3" = Marilao    (KM 23),  "4" = Bocaue       (KM 27)
# -----------------------------------------------------------------------
INTERCHANGE_NAMES = {
    ("ENTRY", "1"): "Balintawak",
    ("ENTRY", "2"): "Mindanao Ave",
    ("EXIT",  "3"): "Valenzuela",
    ("EXIT",  "4"): "Meycauayan",
    ("EXIT",  "5"): "Marilao",
    ("EXIT",  "6"): "Bocaue",
}

# dsistance-based fare matrix (entry_lane, exit_lane) -> PHP fare
FARE_MATRIX = {
    # Balintawak (KM 12) entries
    ("1", "3"): 50.50,   # Balintawak -> Valenzuela   3.0 km
    ("1", "4"): 64.50,   # Balintawak -> Meycauayan   7.0 km
    ("1", "5"): 78.50,   # Balintawak -> Marilao     11.0 km
    ("1", "6"): 92.50,   # Balintawak -> Bocaue       15.0 km
    # Mindanao Ave (KM 13.5) entries
    ("2", "3"): 45.25,   # Mindanao Ave -> Valenzuela  1.5 km
    ("2", "4"): 59.25,   # Mindanao Ave -> Meycauayan  5.5 km
    ("2", "5"): 73.25,   # Mindanao Ave -> Marilao     9.5 km
    ("2", "6"): 87.25,   # Mindanao Ave -> Bocaue     13.5 km
    # Tinuos ko isa-isa yan fr
}


def interchange_name(gate_type: str, lane_id: str) -> str:
    return INTERCHANGE_NAMES.get((gate_type.upper(), str(lane_id)), f"Lane {lane_id}")


class TollwayEngine:
    def __init__(self, db: TollwayDB):
        self.db = db
    def process_scan(self, gate_type: str, lane_id: str, rfid_uid: str) -> dict:
        gate_type = gate_type.upper()
        account = self.db.find_by_uid(rfid_uid)
        if gate_type == "ENTRY":
            return self._process_entry(lane_id, rfid_uid, account)
        elif gate_type == "EXIT":
            return self._process_exit(lane_id, rfid_uid, account)
        else:
            return self._result(lane_id, gate_type, DENY, "BAD_GATE_TYPE", None, None, None)
    def _process_entry(self, lane_id, rfid_uid, account):
        if account is None:
            account = self.db.register_account(rfid_uid, is_inside=True, entry_lane=lane_id)
            return self._result(lane_id, "ENTRY", GRANT, "NEW",
                                 account["vehicle_number"], account["balance"], True)
        if account["is_inside"]:
            return self._result(lane_id, "ENTRY", DENY, "ALREADY_INSIDE",
                                 account["vehicle_number"], account["balance"], True)
        self.db.set_inside(account["vehicle_number"], True)
        self.db.set_entry_lane(account["vehicle_number"], lane_id)
        return self._result(lane_id, "ENTRY", GRANT, "OK",
                             account["vehicle_number"], account["balance"], True)
    def _process_exit(self, lane_id, rfid_uid, account):
        if account is None:
            return self._result(lane_id, "EXIT", DENY, "UNKNOWN", None, None, None)
        if not account["is_inside"]:
            return self._result(lane_id, "EXIT", DENY, "GHOST_CAR",
                                 account["vehicle_number"], account["balance"], False)
        fare = FARE_MATRIX.get((account["entry_lane"], lane_id), DEFAULT_FARE)

        updated = self.db.adjust_balance(account["vehicle_number"], -fare)
        self.db.set_inside(account["vehicle_number"], False)
        self.db.set_entry_lane(account["vehicle_number"], None)  # trip settled
        self.db.log_transaction(account["vehicle_number"], lane_id, "EXIT", fare)

        if updated["balance"] < 0:
            return self._result(lane_id, "EXIT", GRANT, "PENALTY",
                                 account["vehicle_number"], updated["balance"], False, fare)
        return self._result(lane_id, "EXIT", GRANT, "OK",
                             account["vehicle_number"], updated["balance"], False, fare)

    def process_recharge(self, vehicle_number: int, delta: int) -> dict:

        account = self.db.find_by_vehicle_number(vehicle_number)
        if account is None:
            return {"ok": False, "reason": f"Vehicle {vehicle_number} not found"}
        updated = self.db.adjust_balance(vehicle_number, delta)
        return {"ok": True, "vehicle_number": vehicle_number,
                "delta": delta, "balance": updated["balance"]}

    @staticmethod
    def _result(lane_id, gate_type, status, reason, vehicle_number, balance, is_inside, fare_charged=None):
        return {
            "lane_id": lane_id,
            "gate_type": gate_type,
            "interchange": interchange_name(gate_type, lane_id),
            "status": status,
            "reason": reason,
            "vehicle_number": vehicle_number,
            "balance": balance,
            "is_inside": is_inside,
            "fare_charged": fare_charged,
        }
