import straders_sdk
from flask_socketio import SocketIO, send, emit
from straders_sdk.clients import SpaceTradersMediatorClient
from straders_sdk.pathfinder import PathFinder
import time

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
        send("Destination not found -" + destination.error_code)
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
        time.sleep(ship.nav.travel_time_remaining)

        ship.nav.status = "ORBIT"
        client.update(ship)
        send("Ship arrived")

    elif distance < ship.fuel_capacity:
        send(
            f"Single hop route - {distance}u, {travel_time} refueling then going direct"
        )
    else:
        send("Multi-hop route")
