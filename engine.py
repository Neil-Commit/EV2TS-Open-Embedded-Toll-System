"""
Mostly logics and how rfid reacts to different scanss

    [ Gate == ENTRY ]                    [ Gate == EXIT ]
    Does account exist?                  Does account exist?
      NO  -> Register & GRANT,             NO  -> DENY (Unknown)
             stamp entry_lane              YES -> is_inside?
      YES -> is_inside?                           NO  -> DENY (Ghost Car)
              YES -> DENY (already in)             YES -> look up fare by
              NO  -> GRANT,                               (entry_lane, exit_lane),
                     stamp entry_lane                      deduct it, mark OUT,
                                                            GRANT (PENALTY if
                                                            balance goes negative

Mark idea of UTurn cars still not implemented, optimization muna

"""

from database import TollwayDB, EXIT_COST

GRANT = "GRANT"
DENY = "DENY"
DEFAULT_FARE = EXIT_COST  # pag hindi alam yung entry_lane

# Distance base northbound kunwari -> IN1 ... IN2 ... EX1 ... EX2 ->
FARE_MATRIX = {
    ("1", "1"): 100,  # IN1 -> EX1 (medium)
    ("1", "2"): 200,  # IN1 -> EX2 (farthest)
    ("2", "1"): 50,   # IN2 -> EX1 (closest)
    ("2", "2"): 120,  # IN2 -> EX2 (medium-long)
}


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
            # Dynamic Reg rule
            account = self.db.register_account(rfid_uid, is_inside=True, entry_lane=lane_id)
            return self._result(lane_id, "ENTRY", GRANT, "NEW",
                                 account["vehicle_number"], account["balance"], True)

        if account["is_inside"]:
            # Not allow double entry =========== [May change in the future >mark idea]
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
            # Na scan sa exit pero hindi nag entry
            return self._result(lane_id, "EXIT", DENY, "GHOST_CAR",
                                 account["vehicle_number"], account["balance"], False)

        # Fare logic matrix
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
        """Balance adjustment for simulation and top-ups"""
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
            "status": status,
            "reason": reason,
            "vehicle_number": vehicle_number,
            "balance": balance,
            "is_inside": is_inside,
            "fare_charged": fare_charged,
        }
