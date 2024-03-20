import straders_sdk.models as st_models
import straders_sdk.constants as st_constants
import straders_sdk.clients as st_clients
import straders_sdk.utils as st_utils
import threading
import json
import time


class MiningManager:

    # singleton class

    _instance = None

    def __new__(cls, client: st_clients.SpaceTradersMediatorClient):
        if cls._instance is None:
            cls._instance = super(MiningManager, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self, client: st_clients.SpaceTradersMediatorClient):
        if hasattr(self, "__initialized"):
            return
        self.__initialized = True
        self.mining_sites: dict[str:MiningSite] = {}
        self.client = client
        self.load_self()

    def register_asteroid(
        self,
        waypoint: st_models.Waypoint,
        client: st_clients.SpaceTradersMediatorClient,
    ):
        if waypoint.symbol in self.mining_sites:
            return
        self.mining_sites[waypoint.symbol] = MiningSite(waypoint, client)

    def init_starting_asteroids(self):
        agent = self.client.view_my_self()
        if not agent:
            return
        hq_system = st_utils.waypoint_to_system(agent.headquarters)
        waypoints = self.client.find_waypoints_by_type(hq_system, "GAS_GIANT")
        for waypoint in waypoints:
            self.register_asteroid(waypoint, self.client)

        waypoints = self.client.find_waypoints_by_type(hq_system, "ENGINEERED_ASTEROID")
        for waypoint in waypoints:
            self.register_asteroid(waypoint, self.client)

        self.save_self()

    def load_self(self):
        try:
            with open("resources/mining_manager.json", "r+") as f:
                data = json.load(f)

            for k, v in data.items():
                wp = self.client.waypoints_view_one(k)
                self.mining_sites[k] = MiningSite(wp, self.client)
                self.mining_sites[k].refresh_from_dict(v)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            if len(self.mining_sites) == 0:
                self.init_starting_asteroids()

    def save_self(self):
        with open("resources/mining_manager.json", "w+") as f:
            data = {k: v.to_dict() for k, v in self.mining_sites.items()}
            json.dump(data, f, indent=4)


class MiningSite:

    def __init__(
        self,
        waypoint: st_models.Waypoint,
        client: st_clients.SpaceTradersMediatorClient,
    ):
        self.waypoint = waypoint
        self.waypoint_symbol = waypoint.symbol
        self.ships = {}
        self.active_thread = None
        if "ASTEROID" in waypoint.type:
            self.extractables = st_constants.EXTRACTABLES
            self.extractable_destinations = {e: [] for e in self.extractables}
        elif waypoint.type == "GAS_GIANT":
            self.extractables = st_constants.SHIPONABLES
            self.extractable_destinations = {e: [] for e in self.extractables}
        else:
            self.extractables = []
            self.extractable_destinations = {}
        token = client.token
        connection_pool = client.db_client.connection_pool
        self.client = st_clients.SpaceTradersMediatorClient(
            token,
            db_host=connection_pool.db_host,
            db_port=connection_pool.db_port,
            db_name=connection_pool.db_name,
            db_user=connection_pool.db_user,
            db_pass=connection_pool.db_pass,
            priority=4,
        )

        self.active_thread = threading.Thread(
            target=self.execute_extractions, daemon=True, args=(waypoint.type,)
        )
        self.active_thread.start()

        # we need to make a new client from the old one.

    def register_ship(self, ship: st_models.Ship):
        self.ships[ship.symbol] = ship
        pass

    def to_dict(self):
        return {
            "waypoint": self.waypoint_symbol,
            "extractables": self.extractables,
            "extractable_destinations": self.extractable_destinations,
            "registered_ships": [s.symbol for s in self.ships.values()],
        }

    def refresh_from_dict(self, data):
        self.waypoint_symbol = data["waypoint"]
        self.extractables = data["extractables"]
        self.extractable_destinations = data["extractable_destinations"]
        self.ships = {
            s: self.client.ships_view_one(s) for s in data["registered_ships"]
        }

    def execute_extractions(self, type="ASTEROID"):
        extraction_method = (
            self.client.ship_siphon if type == "GAS_GIANT" else self.client.ship_extract
        )
        while True:
            delays = {
                "ASTEROID": 6,
                "ENGINEERED_ASTEROID": 3,
                "GAS_GIANT": 0,
            }
            best_cooldown = delays.get(type, 6)
            ships = self.client.ships_view()
            if not ships:
                time.sleep(60)
                continue
            local_ships = [
                s
                for s in ships.values()
                if s.nav.waypoint_symbol == self.waypoint_symbol
            ]

            extracted = False
            for ship in local_ships:
                ship: st_models.Ship
                if not ship.nav.travel_time_remaining == 0:
                    continue
                if not ship.can_extract and not ship.can_siphon:
                    continue
                if ship.seconds_until_cooldown > 0:
                    best_cooldown = max(best_cooldown, ship.seconds_until_cooldown)
                    continue
                if ship.cargo_space_remaining == 0:
                    continue
                extracted = extraction_method(ship)
                if extracted:
                    print(f"ship {ship.name} extracted at {self.waypoint_symbol}")
                break
            if not extracted:
                time.sleep(best_cooldown)

        # total number of ships on site * their cooldown = total consumption time
        # assuming a max of 10 extractions a minute,
        # find a ship with empty cargo space that's on site, and execute extraction. Wait 6 seconds, repeat.
        # if engineered asteroid, 3 secodns.
        # once every 60 seconds, check for new ships on site.

        pass

    def execute_sell_orders(self):
        # for any ship that's full, or not on site, execute any relevant sell order, and return to the site.

        pass

    def transfer_to_hauler(self, trade_symbol, ship_symbol):
        # a hauler that arrives can call this to shift all relevant goods to the hauler.
        # transfer and update the trade manager
        pass

    def update_trade_manager(self, trade_symbol, ship_symbol, action):
        # update the relevant opportunities whenever new material is gathered.
        # assume that materials will be deducted by the thing being done.
        pass
