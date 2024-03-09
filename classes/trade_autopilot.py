import classes.ship_handler_functions as shf
import classes.ship_locker as sl
import classes.trademanager as tm
import straders_sdk.clients as st_clients
import straders_sdk.models as st_models
import straders_sdk.utils as st_utils
import threading
import time
import json, os


class TradeAutoPilot:
    "singleton class to manage the trade autopilot."

    def __new__(cls, ship_controller: shf.ShipHandler):
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, ship_controller: shf.ShipHandler):
        if hasattr(self, "tm"):
            return
        self.ship_controller = ship_controller
        self.client = self.ship_controller.client
        self.tm = tm.TradeManager(self.client)
        self._ships = {}
        self._loop_thread = None
        self._locker = sl.ShipLocker()
        self.load_autopilot()
        self.run()

    def register_ship(self, ship_id: str, save=True):
        self._ships[ship_id] = {"thread": None}
        if save:
            self.save_autopilot()

    def unregister_ship(self, ship_id: str):
        self._ships.pop(ship_id, None)
        self.save_autopilot()

    def toggle_ship(self, ship_id: str):
        "Returns True if the ship is now being autopiloted, False if it's not."
        if ship_id in self._ships:
            self.unregister_ship(ship_id)
            return False
        else:
            self.register_ship(ship_id)
            return True

    def is_ship_autopiloting(self, ship_id: str) -> bool:
        return ship_id in self._ships

    def run(self):
        if self._loop_thread:
            return

        self._loop_thread = threading.Thread(target=self._run)
        self._loop_thread.start()

    def _run(self):
        while True:
            time.sleep(1)
            for ship_id, ship_d in self._ships.items():
                if self._locker.is_ship_locked(ship_id):
                    continue
                if ship_d and ship_d["thread"] and ship_d["thread"].is_alive():
                    continue

                thread = threading.Thread(
                    target=self.ship_controller.execute_best_trade,
                    args=(ship_id,),
                )
                ship_d["thread"] = thread
                thread.start()
                # if it's not locked, start a thread for the ship.

    def load_autopilot(self):
        # load the autopilot from a file
        if not os.path.exists("resources/autopilot.json"):
            return
        with open("resources/autopilot.json", "r") as f:
            ships = json.load(f)
            for ship in ships:
                self.register_ship(ship, False)

        ships = self.client.ships_view()
        for ship_symbol, ship in ships.items():
            # if the ship is moving, or has cargo, we need to leave it be.
            ship: st_models.Ship
            if ship.nav.travel_time_remaining >= 0 or ship.cargo_units_used > 0:

                self.unregister_ship(ship.name)

    def save_autopilot(self):
        # save the autopilot to a file
        with open("resources/autopilot.json", "w") as f:
            json.dump([s for s in self._ships.keys()], f)
