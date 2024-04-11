import straders_sdk.models as st_models
import straders_sdk.constants as st_constants
import straders_sdk.clients as st_clients
import straders_sdk.utils as st_utils
import straders_sdk.pathfinder as st_pathfinder

import logging
import classes.ship_handler_functions as shf
import threading
import json
import time
import queue
import classes.ship_locker as sl


class MiningManager:

    # singleton class

    _instance = None

    def __new__(cls, client: st_clients.SpaceTradersMediatorClient, socket_context):
        if cls._instance is None:
            cls._instance = super(MiningManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, client: st_clients.SpaceTradersMediatorClient, socket_context):
        if hasattr(self, "_enabled_already"):
            return
        self._enabled_already = True
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

    def to_json(self):
        return_obj = {}
        return_obj["sites"] = {k: v.to_dict() for k, v in self.mining_sites.items()}

    def load_self(self):
        try:
            with open("resources/mining_manager.json", "r+") as f:
                data = json.load(f)

            for k, v in data.items():
                wp = self.client.waypoints_view_one(k)
                # if the site exists already, refresh it from the data.
                if k not in self.mining_sites:
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
        registered_ship_symbols: list[str] = None,
    ):
        self.sh = handler
        self.waypoint = waypoint

        self.waypoint_symbol = waypoint.symbol
        self.logger = logging.getLogger("MiningSite")
        self.registered_ships = registered_ship_symbols or []
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
            target=self.execute_extractions,
            daemon=True,
            args=(waypoint.type,),
            name=f"extractor_thread_{waypoint.symbol}",
        )
        self.extractor_thread.start()

        self.sell_thread = threading.Thread(
            target=self.execute_sell_orders,
            daemon=True,
            name=f"sell_thread_{waypoint.symbol}",
        )
        self.sell_thread.start()
        self.sell_queue = queue.Queue()
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
        self.registered_ships = data["registered_ships"]
        self.ships = {s: self.client.ships_view_one(s) for s in self.registered_ships}

        ss = st_models.SingletonShips()
        for ship in self.ships.values():
            if ship is not ss.get_ship(ship.name):
                ss.add_ship(ship)

    def execute_extractions(self, type="ASTEROID"):
        extraction_method = (
            self.client.ship_siphon if type == "GAS_GIANT" else self.client.ship_extract
        )
        locker = sl.ShipLocker()
        while True:
            delays = {
                "ASTEROID": 6,
                "ENGINEERED_ASTEROID": 3,
                "GAS_GIANT": 0.1,
            }
            best_cooldown = delays.get(type, 6)
            ships = self.ships

            # this is not returning cooldown information
            if not ships:
                time.sleep(60)
                continue

            local_ships = [
                s.name
                for s in ships.values()
                if s.nav.waypoint_symbol == self.waypoint_symbol
            ]

            if not local_ships:
                best_cooldown = 60
            ship_singleton = st_models.SingletonShips()
            extracted = False
            for ship_symbol in local_ships:
                ship = self.ships[ship_symbol]
                if ship is not ship_singleton.get_ship(ship_symbol):
                    ship = ship_singleton.add_ship(ship)

                ship: st_models.Ship

                if not ship.nav.travel_time_remaining == 0:
                    continue
                if not ship.can_extract and not ship.can_siphon:
                    continue
                if (
                    ship.cargo_space_remaining == 0
                    and ship not in self.sell_queue.queue
                ):
                    # self.sh.socket.send(f"Added {ship.name} to sell queue.")
                    self.sell_queue.put(ship)
                    time.sleep(0.5)

                if ship.seconds_until_cooldown > 0:
                    best_cooldown = min(best_cooldown, ship.seconds_until_cooldown)
                    continue
                lock = locker.lock_ship(ship.name, 5)
                if not lock:
                    continue
                extracted = extraction_method(ship)
                if extracted:
                    # success! finish up and break the loop and wait for next ship.
                    self.logger.info("ship %s extracted successfully", ship.name)
                    best_cooldown = delays.get(type, 6)
                    self.sh.socket.emit("ship-update", shf.ship_to_dict(ship))
                    locker.unlock_early(ship.name)
                    break
                elif extracted.error_code in [4000]:
                    ship = self.client.ships_view_one(ship.name, True)
                else:
                    ship = self.client.ships_view_one(ship.name)
                locker.unlock_early(ship.name)
            # summon ships to the site
            for ship in ships.values():
                if ship.name in local_ships:
                    continue

                if ship not in self.sell_queue.queue:
                    self.sell_queue.put(ship)
                else:
                    best_cooldown = max(best_cooldown, 1)
                    # we've hit this too often, sleep for at least a sec (we might be at a gas giant )

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
        time.sleep(1)
        ship_singleton = st_models.SingletonShips()
        while True:

            if self.sell_queue.not_empty:
                ship = self.sell_queue.get()

                ship: st_models.Ship
                ship_symbol = ship.name

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

                if len(ship.cargo_inventory) == 0 and ship.cargo_units_used > 0:
                    ship = self.client.ships_view_one(ship_symbol, True)
                else:
                    ship = self.client.ships_view_one(ship_symbol)
                # sell full ships
                # this is happening for ships that are in transit.
                if ship.cargo_space_remaining == 0:
                    self.sh.socket.send(
                        f"Mining site {self.waypoint_symbol} is ordering {ship.name} to sell goods."
                    )
                    thread = threading.Thread(
                        target=self._execute_sell_order,
                        args=(ship,),
                        name=f"sell_order {ship.name}",
                    )
                    ships_and_threads[ship.name] = thread
                    thread.start()

                # bring back ships that are not on site
                if (
                    ship.cargo_space_remaining > 0
                    and ship.nav.waypoint_symbol != self.waypoint_symbol
                ):
                    self.sh.socket.send(
                        f"Mining site {self.waypoint_symbol} is calling {ship.name}."
                    )
                    thread = threading.Thread(
                        target=self.sh.intrasolar_travel,
                        args=(ship, self.waypoint_symbol),
                        name=f"return to site {ship.name}",
                    )
                    ships_and_threads[ship.name] = thread
                    thread.start()
                    pass

            else:
                time.sleep(1)

    def _execute_sell_order(self, ship: st_models.Ship):
        # check the destinations for each tradegood in the ship cargo, then go to each destination and sell the goods.
        # on completion, rtb.

        # check if the current thread is the one that's supposed to be running this ship.

        locker = sl.ShipLocker()
        lock = locker.lock_ship(ship.name, 3600)
        while not lock:
            lock = locker.lock_ship(ship.name, 3600)
            time.sleep(1)
        current_location = self.client.waypoints_view_one(ship.nav.waypoint_symbol)
        if ship.cargo_space_remaining == 0 and len(ship.cargo_inventory) == 0:
            ship = self.client.ships_view_one(ship.name, True)
        for cargo_item in ship.cargo_inventory:
            good = cargo_item.symbol
            destinations = self.extractable_destinations[good]
            if not destinations:
                continue
            best_destination = None
            best_cost_per_distance = 0

            for destination in destinations:
                wayp = self.client.waypoints_view_one(destination)
                market = self.client.system_market(wayp)
                market: st_models.Market
                listing = market.get_tradegood_listing(good)
                if listing is None:
                    continue
                sell_price = listing.sell_price
                distance = self.sh.pathfinder.calc_distance_between(
                    current_location, wayp
                )
                cost_per_distance = sell_price / max(distance, 1)
                if cost_per_distance > best_cost_per_distance:
                    best_cost_per_distance = cost_per_distance
                    best_destination = wayp
            if best_destination is None:
                continue
            self.sh.intrasolar_travel(ship, best_destination.symbol)
            self.sh.sell(ship, good, cargo_item.units)
        self.sh.intrasolar_travel(ship, current_location.symbol)
        locker.unlock_early(ship.name)
        pass

    def transfer_to_hauler(self, trade_symbol, ship_symbol):
        # a hauler that arrives can call this to shift all relevant goods to the hauler.
        # transfer and update the trade manager
        pass

    def update_trade_manager(self, trade_symbol, ship_symbol, action):
        # update the relevant opportunities whenever new material is gathered.
        # assume that materials will be deducted by the thing being done.
        pass
