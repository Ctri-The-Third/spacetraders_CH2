import straders_sdk
from flask_socketio import SocketIO, send, emit
import straders_sdk.models
from straders_sdk.clients import SpaceTradersMediatorClient
from straders_sdk.pathfinder import PathFinder
import time, math
from datetime import datetime, timedelta

# ship_intrasolar
# go_and_buy
# go_and_sell


def intrasolar_travel(client: SpaceTradersMediatorClient, ship_id: str, waypoint: str):

    ship = client.ships_view_one(ship_id)
    destination = client.waypoints_view_one(waypoint)
    pf = PathFinder(client)
    if not ship:
        send(f"Ship not found - {ship.error_code}")
        return
    origin = client.waypoints_view_one(ship.nav.waypoint_symbol)

    if not destination:
        send(f"Destination not found - {destination.error_code}")
        return

    if ship.nav.waypoint_symbol == waypoint:
        send("Already at destination")
        return

    distance = pf.calc_distance_between(origin, destination)
    travel_time = pf.calc_travel_time_between_wps_with_fuel(origin, destination)

    if distance < ship.fuel_current:
        # go direct
        send(f"Single hop route! {distance}u, {travel_time}s -  Skipping pathfinder")
        if ship.nav.status == "DOCKED":
            resp = client.ship_orbit(ship)
            if not resp:
                send("Error orbiting ship - " + resp.error_code)
                return
        resp = client.ship_move(ship, waypoint)
        if not resp:
            send(f"Error moving ship - {resp.error_code}")
            return
        send(f"Ship en route, sleeping for {ship.nav.travel_time_remaining} seconds")
        emit("ship_update", ship_to_dict(ship), broadcast=True)

        time.sleep(ship.nav.travel_time_remaining + 1)

        ship.nav.status = "ORBIT"
        ship.nav_dirty = True
        client.update(ship)
        send("Ship arrived")
        arrive_at_wayp_and_emit(client, waypoint)
        emit("ship_update", ship_to_dict(ship), broadcast=True)

    elif distance < ship.fuel_capacity:
        send(
            f"Single hop route - {distance}u, {travel_time} refueling then going direct"
        )
    else:
        send("Multi-hop route")


def arrive_at_wayp_and_emit(client: SpaceTradersMediatorClient, waypoint_sym: str):
    current_waypoint = client.waypoints_view_one(waypoint_sym)
    if not current_waypoint:
        send(f"Waypoint not found - {current_waypoint.error_code}")
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
        emit("market_update", market_data)
    if current_waypoint.has_shipyard:
        shipyard = client.system_shipyard(current_waypoint)
        emit("shipyard_update", shipyard_to_dict(shipyard))


def buy(client: SpaceTradersMediatorClient, ship_name: str, good: str, quantity: int):
    quantity = int(quantity)

    ship = client.ships_view_one(ship_name)
    if not ship:
        send(f"Ship not found - {ship.error_code}")
        return
    if ship.nav.status != "DOCKED":
        client.ship_dock(ship)
    if quantity == 0:
        quantity = ship.cargo_space_remaining
    market = client.system_market(client.waypoints_view_one(ship.nav.waypoint_symbol))
    market: straders_sdk.models.Market
    tg = market.get_tradegood(good)
    goods_to_buy = min(quantity, ship.cargo_space_remaining)
    tv = tg.trade_volume
    for i in range(math.ceil(goods_to_buy / tv)):
        resp = client.ship_purchase_cargo(ship, tg.symbol, min(tv, goods_to_buy))
        if not resp:
            send(f"Error buying {tg.symbol} - {resp.error_code}")
            emit("ship_update", ship_to_dict(ship), broadcast=True)
            return
        goods_to_buy -= tv
        if goods_to_buy <= 0:
            break
    log_market_changes(client, ship.nav.waypoint_symbol)
    emit("ship_update", ship_to_dict(ship), broadcast=True)


def sell(client: SpaceTradersMediatorClient, ship_name: str, good: str, quantity: int):
    quantity = int(quantity)
    ship = client.ships_view_one(ship_name)
    if not ship:
        send(f"Ship not found - {ship.error_code}")
        return
    found_cargo_item = None
    for c in ship.cargo_inventory:
        if c.symbol == good:
            found_cargo_item = c
            break

    if not found_cargo_item:
        send(f"Ship doesn't have {good} in cargo")
        return
    if ship.nav.status != "DOCKED":
        client.ship_dock(ship)

    waypoint = client.waypoints_view_one(ship.nav.waypoint_symbol)

    market = client.system_market(waypoint)
    market: straders_sdk.models.Market
    tg = market.get_tradegood(good)
    if not tg:
        send(f"Trade good not found - {good}")
        return
    if quantity == 0 or quantity > found_cargo_item.units:
        quantity = found_cargo_item.units
    tv = tg.trade_volume

    for i in range(math.ceil(quantity / tv)):
        amount_to_sell = min(tv, quantity)
        resp = client.ship_sell(ship, tg.symbol, amount_to_sell)
        if not resp:
            send(f"Error selling {tg.symbol} - {resp.error_code}")
            emit("ship_update", ship_to_dict(ship), broadcast=True)
            return
        send(f"Sold {amount_to_sell} of {tg.symbol} for {tv * tg.sell_price} credits")

        quantity -= tv
        if quantity <= 0:
            break
    log_market_changes(client, ship.nav.waypoint_symbol)
    ship = client.ships_view_one(ship_name)
    emit("ship_update", ship_to_dict(ship), broadcast=True)


def refuel(client: SpaceTradersMediatorClient, ship_name: str):
    ship = client.ships_view_one(ship_name)
    if not ship:
        send(f"Ship not found - {ship.error_code}")
        return
    if ship.nav.status != "DOCKED":
        client.ship_dock(ship)

    resp = client.ship_refuel(ship)
    if not resp:
        send(f"Error refueling ship - {resp.error_code}")
        emit("ship_update", ship_to_dict(ship), broadcast=True)
        return
    send("Ship refueled")
    emit("ship_update", ship_to_dict(ship), broadcast=True)


def log_market_changes(client: SpaceTradersMediatorClient, market_s: str):

    wp = client.waypoints_view_one(market_s)
    pre_market = client.system_market(wp)
    pre_market: straders_sdk.models.Market
    post_market = client.system_market(wp, True)
    post_market: straders_sdk.models.Market
    emit("market_update", market_to_dict(post_market), broadcast=True)
    for t in pre_market.listings:
        changes = {}
        nt = post_market.get_tradegood(t.symbol)
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
            client.logging_client.log_custom_event("MARKET_CHANGES", "GLOBAL", changes)


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
        out_obj["tradeGoods"].append(listing)
        stub = {
            "symbol": good.symbol,
            # "name": good.name,
            # "description": good.description,
        }
    for good in market.exports:
        stub = {"symbol": good.symbol}
        out_obj["exports"].append(stub)
    for good in market.imports:
        stub = {"symbol": good.symbol}

        out_obj["imports"].append(stub)
    for good in market.exchange:
        stub = {"symbol": good.symbol}
        out_obj["exchange"].append(stub)
    return out_obj


def shipyard_to_dict(shipyard: straders_sdk.models.Shipyard):
    return {}


def waypoint_to_dict(waypoint: straders_sdk.models.Waypoint):
    return {}


def construction_to_dict(construction: straders_sdk.models.ConstructionSite):
    return {}


def ship_to_dict(ship: straders_sdk.models.Ship):

    return_obj = {
        "symbol": ship.name,
        "registration": {
            "name": ship.name,
            "factionSymbol": "string",
            "role": ship.role,
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
            "condition": ship.frame.condition,
            "moduleSlots": ship.frame.module_slots,
            "mountingPoints": ship.frame.mounting_points,
            "fuelCapacity": ship.fuel_capacity,
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
