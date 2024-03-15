import straders_sdk
from flask_socketio import SocketIO, send, emit
import straders_sdk.models
from straders_sdk.clients import SpaceTradersMediatorClient
from straders_sdk.pathfinder import PathFinder
import straders_sdk.utils as st_utils
import time, math
from datetime import datetime, timedelta
from classes.ship_locker import ShipLocker
import threading
import classes.trademanager as trademanager

# ship_intrasolar
# go_and_buy
# go_and_sell
locker = ShipLocker()


class ShipHandler:
    def __init__(self, client: SpaceTradersMediatorClient, socket: SocketIO):
        self.client = client
        self.socket = socket
        self.pathfinder = PathFinder(client)

    def intrasolar_travel(self, ship_name: str, waypoint: str):
        client = self.client
        if not locker.lock_ship(ship_name, 3600):
            self.socket.send(
                f"Unable to lock {ship_name} for intrasolar travel, expires in {locker.when_does_lock_expire(ship_name)} seconds"
            )

            return
        ship = client.ships_view_one(ship_name)
        destination = client.waypoints_view_one(waypoint)
        pf = self.pathfinder
        if not ship:
            self.socket.send(f"Ship not found - {ship.error_code}")
            locker.unlock_early(ship_name)
            return
        origin = client.waypoints_view_one(ship.nav.waypoint_symbol)

        if not destination:
            self.socket.send(f"Destination not found - {destination.error_code}")
            locker.unlock_early(ship_name)

            return

        if ship.nav.waypoint_symbol == waypoint:
            self.socket.send("Already at destination")
            locker.unlock_early(ship_name)
            return

        distance = pf.calc_distance_between(origin, destination)
        travel_time = pf.calc_travel_time_between_wps_with_fuel(origin, destination)

        if distance < ship.fuel_current or ship.fuel_capacity == 0:
            # go direct
            self._travel_hop(ship, waypoint)

        elif distance < ship.fuel_capacity:

            if self.refuel(ship_name):
                client.ship_orbit(ship)
            self._travel_hop(ship, waypoint)
        else:
            origin = client.waypoints_view_one(ship.nav.waypoint_symbol)
            destination = client.waypoints_view_one(waypoint)
            route = self.pathfinder.plot_system_nav(
                origin.system_symbol,
                origin,
                destination,
                ship.fuel_capacity,
                force_recalc=True,
            )
            if not route or route.needs_drifting:
                self.socket.send("No route found")
                locker.unlock_early(ship_name)
                return
            route.route.pop(0)
            for waypoint_s in route.route:
                next_destination = client.waypoints_view_one(waypoint_s)
                fuel_needed = pf.calc_distance_between(origin, next_destination)
                if ship.fuel_capacity > 0 and (
                    fuel_needed > ship.fuel_current or ship.fuel_current <= 5
                ):
                    if self.refuel(ship_name):
                        client.ship_orbit(ship)
                self._travel_hop(ship, waypoint_s)

        locker.unlock_early(ship_name)

    def force_unlock(self, ship_name: str):
        locker.unlock_early(ship_name, force=True)

    def _travel_hop(self, ship, waypoint):
        client = self.client
        if ship.nav.status != "IN_ORBIT":
            resp = client.ship_orbit(ship)
            if not resp:
                self.socket.send(f"Error orbiting ship - {resp.error_code}")
                return
        resp = client.ship_move(ship, waypoint)
        if not resp:
            self.socket.send(f"Error moving ship - {resp.error_code}")
            return

        self.socket.emit("ship-update", ship_to_dict(ship))
        time.sleep(ship.nav.travel_time_remaining + 1)

        ship.nav.status = "IN_ORBIT"
        ship.nav_dirty = True
        client.update(ship)
        self.socket.send("Ship arrived")
        self.arrive_at_wayp_and_emit(waypoint)
        self.socket.emit("ship-update", ship_to_dict(ship))

    def arrive_at_wayp_and_emit(self, waypoint_sym: str):
        client = self.client
        current_waypoint = client.waypoints_view_one(waypoint_sym)
        if not current_waypoint:
            self.socket.send(f"Waypoint not found - {current_waypoint.error_code}")
            return
        current_waypoint: straders_sdk.models.Waypoint
        if current_waypoint.has_market:
            market = client.system_market(current_waypoint)
            market: straders_sdk.models.Market
            if len(market.listings) == 0 or datetime.now() - market.listings[
                0
            ].recorded_ts > timedelta(minutes=15):
                market = client.system_market(current_waypoint, True)
            market_data = market_to_dict(market)
            self.socket.emit("market-update", market_data)
        if current_waypoint.has_shipyard:
            shipyard = client.system_shipyard(current_waypoint)
            self.socket.emit("shipyard_update", shipyard_to_dict(shipyard))

    def buy(self, ship_name: str, good: str, quantity: int):
        client = self.client
        if not locker.lock_ship(ship_name, 3600):
            self.socket.send(
                f"Unable to lock {ship_name} for cargo buying, expires in {locker.when_does_lock_expire(ship_name)} seconds"
            )
            return
        quantity = math.ceil(float(quantity))

        ship = client.ships_view_one(ship_name)
        if not ship:
            self.socket.send(f"Ship not found - {ship.error_code}")
            locker.unlock_early(ship_name)
            return
        if ship.nav.status != "DOCKED":
            client.ship_dock(ship)
        if quantity == 0:
            quantity = ship.cargo_space_remaining
        market = client.system_market(
            client.waypoints_view_one(ship.nav.waypoint_symbol)
        )
        market: straders_sdk.models.Market
        if not market:
            self.socket.send(f"Market not found - {market.error_code}")
            locker.unlock_early(ship_name)
            return
        tg = market.get_tradegood_listing(good)
        if not hasattr(tg, "trade_volume"):
            market = client.system_market(
                client.waypoints_view_one(ship.nav.waypoint_symbol), True
            )
            tg = market.get_tradegood_listing(good)
        goods_to_buy = min(quantity, ship.cargo_space_remaining)
        if not tg:
            self.socket.send(f"Trade good not found - {good}")
            locker.unlock_early(ship_name)
            return
        tv = tg.trade_volume
        for i in range(math.ceil(goods_to_buy / tv)):
            resp = client.ship_purchase_cargo(ship, tg.symbol, min(tv, goods_to_buy))
            if not resp:
                self.socket.send(f"Error buying {tg.symbol} - {resp.error_code}")
                self.socket.emit("ship-update", ship_to_dict(ship))
                self.socket.emit("agent_update", agent_to_dict(client.view_my_self()))
                return
            goods_to_buy -= tv
            if goods_to_buy <= 0:
                break
        self.log_market_changes(ship.nav.waypoint_symbol)
        self.socket.emit("ship-update", ship_to_dict(ship))
        self.socket.emit("agent_update", agent_to_dict(client.view_my_self()))
        locker.unlock_early(ship_name)

    def sell(self, ship_name: str, good: str, quantity: int):
        client = self.client
        if not locker.lock_ship(ship_name, 3600):
            self.socket.send(
                f"Unable to lock {ship_name} for cargo selling, expires in {locker.when_does_lock_expire(ship_name)} seconds"
            )
            return
        quantity = math.ceil(float(quantity))
        ship = client.ships_view_one(ship_name)
        if not ship:
            self.socket.send(f"Ship not found - {ship.error_code}")
            locker.unlock_early(ship_name)
            return
        found_cargo_item = None
        for c in ship.cargo_inventory:
            if c.symbol == good:
                found_cargo_item = c
                break

        if not found_cargo_item:
            self.socket.send(f"Ship doesn't have {good} in cargo")
            locker.unlock_early(ship_name)
            return
        if ship.nav.status != "DOCKED":
            client.ship_dock(ship)

        waypoint = client.waypoints_view_one(ship.nav.waypoint_symbol)

        market = client.system_market(waypoint)
        market: straders_sdk.models.Market
        tg = market.get_tradegood_listing(good)
        if not tg:
            self.socket.send(f"Trade good not found - {good}")
            locker.unlock_early(ship_name)
            return
        if quantity == 0 or quantity > found_cargo_item.units:
            quantity = found_cargo_item.units
        tv = tg.trade_volume

        for i in range(math.ceil(quantity / tv)):
            amount_to_sell = min(tv, quantity)
            resp = client.ship_sell(ship, tg.symbol, amount_to_sell)
            if not resp:
                self.socket.send(f"Error selling {tg.symbol} - {resp.error_code}")
                self.socket.emit("ship-update", ship_to_dict(ship))
                self.socket.emit("agent_update", agent_to_dict(client.view_my_self()))
                locker.unlock_early(ship_name)
                return
            self.socket.send(
                f"Sold {amount_to_sell} of {tg.symbol} for {tv * tg.sell_price} credits"
            )

            quantity -= tv
            if quantity <= 0:
                break
        self.log_market_changes(ship.nav.waypoint_symbol)
        ship = client.ships_view_one(ship_name)
        self.socket.emit("ship-update", ship_to_dict(ship))
        self.socket.emit("agent_update", agent_to_dict(client.view_my_self()))
        locker.unlock_early(ship_name)

    def execute_best_trade(self, ship_symbol):
        client = self.client
        ship = client.ships_view_one(ship_symbol)
        tm = trademanager.TradeManager(client)
        trade = tm.pick_best_trade(
            ship.nav.system_symbol,
            ship.nav.waypoint_symbol,
            ship.fuel_capacity,
            ship.cargo_capacity,
        )
        if not trade:
            self.socket.send(f"Couldn't find a trade for ship {ship.name}")
            return

        if not trade.end_location:
            self.socket.send(f"Trade {trade.trade_symbol} end location not found")
            return
        trade: trademanager.TradeOpportunity
        projected_profit = trade.profit_per_unit * min(
            trade.total_quantity, ship.cargo_capacity
        )

        self.socket.send(
            f"Found best trade for {ship.name} - {trade.trade_symbol}, {projected_profit}cr for {trade.distance} units."
        )
        self.execute_trade(
            ship.name,
            trade.trade_symbol,
            trade.start_location.symbol,
            trade.end_location.symbol,
            trade.total_quantity,
        )

    def execute_trade(
        self,
        ship_name: str,
        trade_symbol: str,
        start_location: str,
        end_location: str,
        quantity: int,
    ):
        client = self.client
        ship = client.ships_view_one(ship_name)
        tm = trademanager.TradeManager(client)
        quantity = min(math.ceil(float(quantity)), ship.cargo_space_remaining)

        tm.claim_trade(trade_symbol, start_location, end_location, quantity)
        self.socket.emit("trades-update", tm.list_opportunities_for_json())
        self.intrasolar_travel(ship_name, start_location)
        self.buy(ship_name, trade_symbol, quantity)
        self.socket.emit("trades-update", tm.list_opportunities_for_json())
        self.intrasolar_travel(ship_name, end_location)
        self.sell(ship_name, trade_symbol, quantity)
        # need to instruct the
        self.socket.send("Trade complete")
        self.socket.emit("trades-update", tm.list_opportunities_for_json())

        locker.unlock_early(ship_name)

    def refuel(self, ship_name: str) -> bool:
        "Returns true if you need to undock"
        client = self.client
        ship = client.ships_view_one(ship_name)
        if not ship:
            self.socket.send(f"Ship not found - {ship.error_code}")
            return False
        if ship.nav.status != "DOCKED":
            client.ship_dock(ship)

        resp = client.ship_refuel(ship)
        if not resp:
            self.socket.send(f"Error refueling ship - {resp.error_code}")
            self.socket.emit("ship-update", ship_to_dict(ship))
            return True
        self.socket.send("Ship refueled")
        self.socket.emit("ship-update", ship_to_dict(ship))
        return True

    def log_market_changes(self, market_s: str):
        client = self.client
        wp = client.waypoints_view_one(market_s)
        pre_market = client.system_market(wp)
        pre_market: straders_sdk.models.Market
        post_market = client.system_market(wp, True)
        tm = trademanager.TradeManager(client)
        tm.update_market(post_market)
        post_market: straders_sdk.models.Market
        self.socket.emit("trades-update", tm.list_opportunities_for_json())
        self.socket.emit("market-update", market_to_dict(post_market))
        for t in pre_market.listings:
            changes = {}
            nt = post_market.get_tradegood_listing(t.symbol)
            if not isinstance(nt, straders_sdk.models.MarketTradeGoodListing):
                continue

            if nt.purchase_price != t.purchase_price:
                changes["purchase_price_change"] = nt.purchase_price - t.purchase_price
            if nt.sell_price != t.sell_price:
                changes["sell_price_change"] = nt.sell_price - t.sell_price
            if nt.supply != t.supply:
                changes["old_supply"] = t.supply
            if nt.activity != t.activity:
                changes["old_activity"] = t.activity
            if nt.trade_volume != t.trade_volume:
                changes["trade_volume_change"] = nt.trade_volume - t.trade_volume

            if len(changes) > 0:
                changes["purchase_price"] = nt.purchase_price
                changes["sell_price"] = nt.sell_price
                changes["supply"] = nt.supply
                changes["activity"] = nt.activity
                changes["trade_volume"] = nt.trade_volume
                changes["trade_symbol"] = t.symbol
                changes["market_symbol"] = market_s
                client.logging_client.log_custom_event(
                    "MARKET_CHANGES", "GLOBAL", changes
                )

    def market_to_dict(self, market: straders_sdk.models.Market):
        return market_to_dict(market)

    def ship_to_dict(self, ship: straders_sdk.models.Ship):
        return ship_to_dict(ship)

    def agent_to_dict(self, agent: straders_sdk.models.Agent):
        return agent_to_dict(agent)

    def shipyard_to_dict(self, shipyard: straders_sdk.models.Shipyard):
        return shipyard_to_dict(shipyard)

    def waypoint_to_dict(self, waypoint: straders_sdk.models.Waypoint):
        return waypoint_to_dict(waypoint)

    def construction_to_dict(self, construction: straders_sdk.models.ConstructionSite):
        return construction_to_dict(construction)


def market_to_dict(market: straders_sdk.models.Market):
    out_obj = {
        "symbol": market.symbol,
        "exports": [],
        "imports": [],
        "exchange": [],
        "transactions": [],
        "tradeGoods": [],
    }
    for good in market.listings:
        listing = {
            "symbol": good.symbol,
            "type": good.type,
            "tradeVolume": good.trade_volume,
            "supply": good.supply,
            "activity": good.activity,
            "purchasePrice": good.purchase_price,
            "sellPrice": good.sell_price,
        }
        tradegood = market.get_tradegood(good.symbol)
        listing["name"] = tradegood.name
        listing["description"] = tradegood.description
        out_obj["tradeGoods"].append(listing)

        # sort by exports, imports, exchange
    out_obj["tradeGoods"].sort(key=lambda x: x["type"])
    for good in market.exports:
        stub = {
            "symbol": good.symbol,
            "name": good.name,
            "description": good.description,
        }
        out_obj["exports"].append(stub)
    for good in market.imports:
        stub = {
            "symbol": good.symbol,
            "name": good.name,
            "description": good.description,
        }

        out_obj["imports"].append(stub)
    for good in market.exchange:
        stub = {
            "symbol": good.symbol,
            "name": good.name,
            "description": good.description,
        }
        out_obj["exchange"].append(stub)
    return out_obj


def shipyard_to_dict(shipyard: straders_sdk.models.Shipyard):
    if shipyard:
        return shipyard.to_json()
    return {}


def waypoint_to_dict(waypoint: straders_sdk.models.Waypoint):
    return_obj = waypoint.to_json()
    return_obj["has_market"] = waypoint.has_market
    return_obj["has_shipyard"] = waypoint.has_shipyard
    return_obj["has_construction"] = waypoint.under_construction
    return_obj["traits_friendly"] = ", ".join([t.symbol for t in waypoint.traits])
    return_obj["symbol_suffix"] = st_utils.waypoint_suffix(waypoint.symbol)
    return_obj["orbitals_friendly"] = ", ".join(
        [st_utils.waypoint_suffix(o["symbol"]) for o in waypoint.orbitals]
    )
    return return_obj


def construction_to_dict(construction: straders_sdk.models.ConstructionSite):
    return {}


def map_role(role) -> str:
    roles = {
        "COMMAND": "👑",
        "EXCAVATOR": "⛏️",
        "HAULER": "🚛",
        "TRANSPORT": "🚚",
        "SURVEYOR": "🔬",
        "SATELLITE": "🛰️",
        "REFINERY": "⚙️",
        "EXPLORER": "🗺️",
    }
    return roles.get(role, role)


def map_frame(frame) -> str:
    frames = {
        "FRAME_DRONE": "⛵",
        "FRAME_PROBE": "⛵",
        "FRAME_SHUTTLE": "⛵",
        "FRAME_MINER": "🚤",
        "FRAME_LIGHT_FREIGHTER": "🚤",
        "FRAME_EXPLORER": "🚤",
        "FRAME_FRIGATE": "🚤",
        "FRAME_HEAVY_FREIGHTER": "⛴️",
    }
    return frames.get(frame, frame)


def ship_to_dict(ship: straders_sdk.models.Ship):

    return_obj = {
        "symbol": ship.name,
        "registration": {
            "name": ship.name,
            "factionSymbol": "string",
            "role": ship.role,
            "emoji": map_role(ship.role),
        },
        "nav": {
            "systemSymbol": ship.nav.system_symbol,
            "waypointSymbol": ship.nav.waypoint_symbol,
            "route": {
                "destination": {},
                "origin": {},
                "departureTime": "2019-08-24T14:15:22Z",
                "arrival": "2019-08-24T14:15:22Z",
            },
            "status": ship.nav.status,
            "flightMode": ship.nav.flight_mode,
            "secondsRemaining": ship.nav.travel_time_remaining,
        },
        "crew": {
            "current": 0,
            "required": 0,
            "capacity": 0,
            "rotation": "STRICT",
            "morale": 0,
            "wages": 0,
        },
        "frame": {
            "symbol": ship.frame.symbol,
            "name": ship.frame.name,
            "description": ship.frame.description,
            "condition": round(ship.frame.condition, 4),
            "integrity": round(ship.frame.integrity, 4),
            "moduleSlots": ship.frame.module_slots,
            "mountingPoints": ship.frame.mounting_points,
            "fuelCapacity": ship.fuel_capacity,
            "emoji": map_frame(ship.frame.symbol),
            "requirements": {
                "power": ship.frame.requirements.power,
                "crew": ship.frame.requirements.crew,
                "slots": ship.frame.requirements.module_slots,
            },
        },
        "reactor": {
            "symbol": ship.reactor.symbol,
            "name": ship.reactor.name,
            "description": ship.reactor.description,
            "condition": ship.reactor.condition,
            "powerOutput": ship.reactor.power_output,
            "requirements": {
                "power": ship.reactor.requirements.power,
                "crew": ship.reactor.requirements.crew,
                "slots": ship.reactor.requirements.module_slots,
            },
        },
        "engine": {
            "symbol": ship.engine.symbol,
            "name": ship.engine.name,
            "description": ship.engine.description,
            "condition": ship.engine.condition,
            "speed": ship.engine.speed,
            "requirements": {
                "power": ship.engine.requirements.power,
                "crew": ship.engine.requirements.crew,
                "slots": ship.engine.requirements.module_slots,
            },
        },
        "cooldown": {
            "shipSymbol": ship.name,
            "totalSeconds": ship._cooldown_length,
            "remainingSeconds": ship.seconds_until_cooldown,
            "expiration": ship._cooldown_expiration,
        },
        "modules": [],
        "mounts": [],
        "cargo": {
            "capacity": ship.cargo_capacity,
            "units": ship.cargo_units_used,
            "inventory": [],
        },
        "fuel": {
            "current": ship.fuel_current,
            "capacity": ship.fuel_capacity,
            "consumed": {"amount": 0, "timestamp": "2019-08-24T14:15:22Z"},
        },
    }
    for cargo in ship.cargo_inventory:
        return_obj["cargo"]["inventory"].append(
            {
                "symbol": cargo.symbol,
                "units": cargo.units,
                "name": cargo.name,
                "description": cargo.description,
            }
        )

    return return_obj


def agent_to_dict(agent: straders_sdk.models.Agent) -> dict:
    return {
        "accountId": agent.account_id,
        "symbol": agent.symbol,
        "headquarters": agent.headquarters,
        "credits": agent.credits,
        "startingFaction": agent.starting_faction,
        "shipCount": agent.ship_count,
    }
