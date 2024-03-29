import straders_sdk.models as st_models
import straders_sdk.constants as st_constants
import straders_sdk.clients as st_clients
import straders_sdk.utils as st_utils
import logging
import classes.ship_handler_functions as shf
import threading
import json
import time


class MiningManager:

    # singleton class

    _instance = None

    def __new__(cls, client: st_clients.SpaceTradersMediatorClient, socket_context):
        if cls._instance is None:
            cls._instance = super(MiningManager, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self, client: st_clients.SpaceTradersMediatorClient, socket_context):
        if hasattr(self, "__initialized"):
            return
        self.__initialized = True
        self.handler = shf.ShipHandler(client, socket_context)
        self.mining_sites: dict[str:MiningSite] = {}
        self.client = client
        # self.load_self()

    def register_asteroid(
        self,
        waypoint: st_models.Waypoint,
        client: st_clients.SpaceTradersMediatorClient,
    ):
        if waypoint.symbol in self.mining_sites:
            return
        self.mining_sites[waypoint.symbol] = MiningSite(waypoint, client, self.handler)

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
                self.mining_sites[k] = MiningSite(wp, self.client, self.handler)
                self.mining_sites[k].refresh_from_dict(v)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            if len(self.mining_sites) == 0:
                self.init_starting_asteroids()
        except Exception as e:
            print(e)

    def save_self(self):
        with open("resources/mining_manager.json", "w+") as f:
            data = {k: v.to_dict() for k, v in self.mining_sites.items()}
            json.dump(data, f, indent=4)


class MiningSite:

    def __init__(
        self,
        waypoint: st_models.Waypoint,
        client: st_clients.SpaceTradersMediatorClient,
        handler: shf.ShipHandler,
    ):
        self.sh = handler
        self.waypoint = waypoint
        self.waypoint_symbol = waypoint.symbol
        self.logger = logging.getLogger("MiningSite")
        self.ships = {}
        self.extractor_thread = None
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
        self.extractor_thread = threading.Thread(
            target=self.execute_extractions, daemon=True, args=(waypoint.type,)
        )
        self.extractor_thread.start()

        self.sell_thread = threading.Thread(
            target=self.execute_sell_orders, daemon=True
        )
        self.sell_thread.start()

        # we need to make a new client from the old one.

    def register_ship(self, ship: st_models.Ship):
        self.ships[ship.name] = ship
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
            # this is not returning cooldown information
            if not ships:
                time.sleep(60)
                continue
            local_ships = [
                s
                for s in ships.values()
                if s.nav.waypoint_symbol == self.waypoint_symbol
            ]
            if not local_ships:
                best_cooldown = 60

            extracted = False
            for ship in local_ships:
                ship: st_models.Ship
                if not ship.nav.travel_time_remaining == 0:
                    continue
                if not ship.can_extract and not ship.can_siphon:
                    continue
                if ship.seconds_until_cooldown > 0:
                    best_cooldown = min(best_cooldown, ship.seconds_until_cooldown)
                    continue
                if ship.cargo_space_remaining == 0:
                    continue
                extracted = extraction_method(ship)
                if extracted:
                    self.logger.info("ship %s extracted successfully", ship.name)
                    best_cooldown = delays.get(type, 6)

            time.sleep(best_cooldown)

        # total number of ships on site * their cooldown = total consumption time
        # assuming a max of 10 extractions a minute,
        # find a ship with empty cargo space that's on site, and execute extraction. Wait 6 seconds, repeat.
        # if engineered asteroid, 3 secodns.
        # once every 60 seconds, check for new ships on site.

        pass

    def execute_sell_orders(self):
        # for any ship that's full, or not on site, execute any relevant sell order, and return to the site.

        # note, having two threads polling the other is not ideal. We will want to switch this to a queue based system where ships that are invalid for extractions (Because they're full or not present) get punted into a queue that the other thread can pick up.
        # then the primary thread can pick them back up as part of that thread's normal operation.
        ships_and_threads = {}
        did_something = True

        while True:
            if not self.ships:
                time.sleep(60)
                continue
            did_something = False
            for ship_symbol, ship in self.ships.items():

                # skip active ships

                if (
                    ship_symbol in ships_and_threads
                    and ships_and_threads[ship_symbol].is_alive()
                ):
                    continue

                # ship ships that are at the site and don't have full cargos
                if (ship.nav.waypoint_symbol == self.waypoint_symbol) and (
                    ship.cargo_space_remaining > 0
                ):
                    continue
                did_something = True
                # refresh from the DB.
                ship = self.client.ships_view_one(ship_symbol)

                # sell full ships
                if ship.cargo_space_remaining == 0:

                    thread = threading.Thread(
                        target=self._execute_sell_order, args=(ship,)
                    )
                    ships_and_threads[ship.name] = thread
                    thread.start()

                # bring back ships that are not on site
                if (
                    ship.cargo_units_used == 0
                    and ship.nav.waypoint_symbol != self.waypoint_symbol
                ):
                    thread = threading.Thread(
                        target=self.sh.intrasolar_travel,
                        args=(ship, self.waypoint_symbol),
                    )
                    ships_and_threads[ship.name] = thread
                    thread.start()
                    pass

            pass
            time.sleep(15)

    def _execute_sell_order(self, ship: st_models.Ship):

        pass

    def transfer_to_hauler(self, trade_symbol, ship_symbol):
        # a hauler that arrives can call this to shift all relevant goods to the hauler.
        # transfer and update the trade manager
        pass

    def update_trade_manager(self, trade_symbol, ship_symbol, action):
        # update the relevant opportunities whenever new material is gathered.
        # assume that materials will be deducted by the thing being done.
        pass
