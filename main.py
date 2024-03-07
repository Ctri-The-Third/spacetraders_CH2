from flask import Flask, render_template, request, redirect
from flask_socketio import SocketIO, send, emit
from functools import wraps
import straders_sdk, straders_sdk.utils, straders_sdk.request_consumer
import straders_sdk.clients, straders_sdk.models
import os
from straders_sdk.clients import SpaceTradersApiClient, SpaceTradersMediatorClient
from straders_sdk.responses import RemoteSpaceTradersRespose
import classes.ship_handler_functions
import time, json
from straders_sdk.utils import waypoint_to_system, waypoint_suffix
from classes.ship_handler_functions import ShipHandler
from classes.trademanager import TradeManager, TradeOpportunity
from classes.trade_autopilot import TradeAutoPilot

app = Flask("C'tri's SpaceTraders Client")
app.config["SECRET_KEY"] = "notreallythatsecret"
socketio = SocketIO(app)

ST_HOST = os.environ.get("ST_DB_HOST", "localhost")
ST_NAME = os.environ.get("ST_DB_NAME", "spacetraders")
ST_USER = os.environ.get("ST_DB_USER", "spacetraders")
ST_PASS = os.environ.get("ST_DB_PASSWORD", "spacetraders")
ST_PORT = os.environ.get("ST_DB_PORT", "5432")

api_client = SpaceTradersApiClient()
mediator_client = SpaceTradersMediatorClient(
    db_host=ST_HOST, db_name=ST_NAME, db_user=ST_USER, db_pass=ST_PASS, db_port=ST_PORT
)
shf = ShipHandler(mediator_client, socketio)


def emit_response(raw_response):
    st_response = RemoteSpaceTradersRespose(raw_response)
    with app.app_context():
        socketio.emit(
            "logs-response",
            f"{st_response.status_code}:{st_response.error_code if not st_response else 0}-{st_response.url}",
        )


straders_sdk.request_consumer.RequestConsumer().register_handler(
    emit_response, "websocket_response"
)


def get_saved_token():
    try:
        with open("token.secret", "r") as f:
            return f.read()
    except FileNotFoundError:
        return None


def check_login(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        token = get_saved_token()
        if token:
            return route(*args, **kwargs)
        else:
            return redirect("/login")

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    params = {}
    params["factions"] = [f for f in mediator_client.list_factions() if f.is_recruiting]

    if request.method == "POST":
        token = request.form.get("agent_token", "")
        params["token"] = token
        agent_name = request.form.get("agent_name")
        params["agent_name"] = agent_name

        success = False
        if token:
            with open("token.secret", "w") as f:
                f.write(token)
                success = True
        elif agent_name:
            resp = api_client.register(
                agent_name,
            )
            if resp:
                with open("token.secret", "w+") as f:
                    f.write(api_client.token)
                    token = api_client.token
                    success = True
            else:
                params["error"] = "Failed to register"
                params["error_detail"] = resp.error
        if success:
            api_client.set_current_agent(agent_name, token)
            mediator_client.set_current_agent(agent_name, token)
            return redirect("/")

    return render_template("login.html", **params)


@app.route("/ships")
@check_login
def ship_list():
    ships = mediator_client.ships_view()
    params = {
        "ships": [shf.ship_to_dict(ship) for ship in ships.values()],
        "agent": shf.agent_to_dict(mediator_client.view_my_self()),
    }
    return render_template("ship_list.html", **params)


@app.route("/ships/<ship_name>")
@check_login
def display_ship_panel(ship_name):
    ship = mediator_client.ships_view_one(ship_name)
    if not ship:
        return "Ship not found"
        # redirect to the ship list page.
    params = {}
    params["ship"] = shf.ship_to_dict(ship)
    waypoint = mediator_client.waypoints_view_one(ship.nav.waypoint_symbol)
    waypoint: straders_sdk.models.Waypoint
    params["waypoint"] = shf.waypoint_to_dict(waypoint)
    if waypoint.has_market:
        market = mediator_client.system_market(waypoint)
        params["market"] = shf.market_to_dict(market)

    if waypoint.has_shipyard:
        shipyard = mediator_client.system_shipyard(waypoint)
        params["shipyard"] = shf.shipyard_to_dict(shipyard)
    if waypoint.under_construction:
        construction = mediator_client.system_construction(waypoint)
        params["construction"] = shf.construction_to_dict(construction)
    return render_template("ship_panel.html", **params)


@app.route("/trades")
@check_login
def view_trade_manager():
    tm = TradeManager(mediator_client)
    params = {}
    ships = mediator_client.ships_view()
    params["trades"] = tm.list_opportunities_for_json()
    params["ships"] = [shf.ship_to_dict(ship) for ship in ships.values()]
    return render_template("trade_list.html", **params)


@app.route("/trade/<system_symbol>/<trade_symbol>")
@check_login
def view_trade(system_symbol, trade_symbol):
    tm = TradeManager(mediator_client)
    trade = tm.get_opportunity_json(system_symbol, trade_symbol)
    return render_template("trade_panel.html", system_symbol=system_symbol, trade=trade)


@socketio.on("save-trade-strategy")
@check_login
def save_trade_strategy(data):
    tm = TradeManager(mediator_client)
    tm.update_strategy(
        data["system_symbol"],
        data["trade_symbol"],
        data["end_location"],
        data["strategy"],
    )
    emit("logs-response", "Trade strategy saved")

    fetch_trade(data)


@socketio.on("travel")
def travel(data):
    # get the ship ID from the data, and the destination
    ship_id = data.get("ship_name")
    destination = data.get("destination")
    shf.intrasolar_travel(ship_id, destination)


@socketio.on("buy")
def buy(data):
    ship_id = data.get("ship_name")
    good = data.get("good")
    quantity = data.get("quantity", 0)
    shf.buy(ship_id, good, quantity)


@socketio.on("sell")
def sell(data):
    ship_id = data.get("ship_name")
    good = data.get("good")
    quantity = data.get("quantity", 0)
    shf.sell(ship_id, good, quantity)


@socketio.on("fetch-markets")
def fetch_markets():
    agent = mediator_client.view_my_self()
    if not agent:
        emit("logs-response", "Agent not found")
        return
    hq = waypoint_to_system(agent.headquarters)
    system = mediator_client.systems_view_one(hq)
    waypoints = mediator_client.find_waypoints_by_trait(hq, "MARKETPLACE")
    for waypoint in waypoints:
        market = mediator_client.system_market(waypoint)


@socketio.on("execute-trade")
def execute_trade(data):
    ship_id = data.get("ship_name")
    trade_symbol = data.get("trade_symbol")
    start_location = data.get("start_location")
    end_location = data.get("end_location")
    quantity = data.get("quantity", 0)
    shf.execute_trade(ship_id, trade_symbol, start_location, end_location, quantity)


@socketio.on("execute-best-trade")
def execute_best_trade(data):
    shf.execute_best_trade(data)


@socketio.on("fetch-market")
def fetch_market(data):
    if not isinstance(data, str):
        send("Invalid data type")
    waypoint = mediator_client.waypoints_view_one(data)
    if not waypoint:
        send(f"Waypoint not found - {waypoint.error_code}")
        return

    market = mediator_client.system_market(waypoint)
    market: straders_sdk.models.Market
    if market.is_stale(15):
        new_market = mediator_client.system_market(waypoint, True)
        # if the new market doesn't have listings (Because a ship isn't present) then stale data is more valuable.
        if new_market.listings:

            market = new_market

    emit("market_update", shf.market_to_dict(market))


@socketio.on("list-ships")
def list_ships():
    # send several events - first, a generic acknolwedgement
    # then a list of ships
    # then finally, a "done" event

    ships = mediator_client.ships_view()
    ship_names = [ship for ship in ships]
    emit("list-ships", ship_names)
    emit("logs-response", "Done listing ships")


@socketio.on("fetch-ship-box")
def fetch_ship_block(data):
    ship = mediator_client.ships_view_one(data, True)
    emit("ship-box", render_template("ship_box.html", ship=shf.ship_to_dict(ship)))


@socketio.on("fetch-ship")
def fetch_ship(data):
    ship = mediator_client.ships_view_one(data, True)
    emit("ship-update", shf.ship_to_dict(ship))


@socketio.on("fetch-trades")
def fetch_trades():
    tm = TradeManager(mediator_client)
    tm.update_opportunities()
    emit("trades-update", tm.list_opportunities_for_json())


@socketio.on("fetch-trade")
def fetch_trade(data):
    tm = TradeManager(mediator_client)
    trade = tm.get_opportunity_json(data["system_symbol"], data["trade_symbol"])
    emit("trade-update", trade)


@socketio.on("fetch-waypoint")
def fetch_waypoint(data):
    waypoint = mediator_client.waypoints_view_one(data)
    output = shf.waypoint_to_dict(waypoint)
    emit("waypoint-update", output)


@app.route("/waypoints/<waypoint_symbol>")
def view_waypoint(waypoint_symbol):
    params = {"waypoint_symbol": waypoint_symbol}
    return render_template("waypoint_panel.html", **params)


@socketio.on("refuel")
# get the "ship_id" from the payload
def refuel(data):
    ship_name = data.get("ship_name")
    # call the refuel function
    shf.refuel(ship_name)


@socketio.on("toggle-autopilot")
def toggle_autopilot(ship_id):

    tap = TradeAutoPilot(shf)
    is_locked = tap.toggle_ship(ship_id)
    emit("autopilot-update", {"ship_id": ship_id, "is_locked": is_locked})


@socketio.on("fetch-ship-autopilotstate")
def fetch_ship_autopilotstate(ship_id):
    tap = TradeAutoPilot(shf)
    is_locked = tap.is_ship_autopiloting(ship_id)
    emit("autopilot-update", {"ship_id": ship_id, "is_locked": is_locked})


@socketio.on("connect")
def test_connect():
    send("Connected to server")


@socketio.on("message")
def handle_message(message):
    print("received message: " + message)
    send("counter-response")


@app.route("/")
@check_login
def index():
    params = {"agent": shf.agent_to_dict(mediator_client.view_my_self())}
    return render_template("index.html", **params)


token = get_saved_token()
if token:
    agent_name = straders_sdk.utils.get_name_from_token(token)
    api_client.set_current_agent(agent_name, token)
    mediator_client.set_current_agent(agent_name, token)


if __name__ == "__main__":
    print("Hello, world!")

    socketio.run(app, host="0.0.0.0", port=3000)
