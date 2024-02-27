from flask import Flask, render_template, request, redirect
from flask_socketio import SocketIO, send, emit
from functools import wraps
import straders_sdk, straders_sdk.utils, straders_sdk.request_consumer
import straders_sdk.clients
import os
from straders_sdk.clients import SpaceTradersApiClient, SpaceTradersMediatorClient
from straders_sdk.responses import RemoteSpaceTradersRespose
import ship_handler_functions as shf
import time
from straders_sdk.utils import waypoint_to_system

app = Flask("C'tri's SpaceTraders Client")
app.config["SECRET_KEY"] = "notreallythatsecret"
socketio = SocketIO(app)

ST_HOST = os.environ.get("ST_DB_HOST", "localhost")
ST_NAME = os.environ.get("ST_DB_NAME", "spacetraders")
ST_USER = os.environ.get("ST_DB_USER", "spacetraders")
ST_PASS = os.environ.get("ST_DB_PASS", "spacetraders")
ST_PORT = os.environ.get("ST_DB_PORT", "5432")


api_client = SpaceTradersApiClient()
mediator_client = SpaceTradersMediatorClient(
    db_host=ST_HOST, db_name=ST_NAME, db_user=ST_USER, db_pass=ST_PASS, db_port=ST_PORT
)


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


"X1-SZ74-K90"
"X1-SZ74-A1"


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

    if request.method == "POST":
        token = request.form.get("token", "")
        params["token"] = token
        agent_name = request.form.get("agent_name")
        params["agent_name"] = agent_name
        if token:
            with open("token.secret", "w") as f:
                f.write(token)
        elif agent_name:
            resp = api_client.register(
                agent_name,
            )
            if resp:
                with open("token.secret", "w+") as f:
                    f.write(api_client.token)
            else:
                params["error"] = "Failed to register"
                params["error_detail"] = resp.error

    return render_template("login.html", **params)


@socketio.on("travel")
def travel(data):
    # get the ship ID from the data, and the destination
    ship_id = data.get("ship_id")
    destination = data.get("destination")
    shf.intrasolar_travel(mediator_client, ship_id, destination)


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


@socketio.on("list-ships")
def list_ships():
    # send several events - first, a generic acknolwedgement
    # then a list of ships
    # then finally, a "done" event

    ships = mediator_client.ships_view()
    ship_names = [ship for ship in ships]
    emit("list-ships", ship_names)
    emit("logs-response", "Done listing ships")


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
    return redirect("/socket_test")


@app.route("/socket_test")
@check_login
def socket_test():
    return render_template("socket_test.html")


token = get_saved_token()
if token:
    agent_name = straders_sdk.utils.get_name_from_token(token)
    api_client.set_current_agent(agent_name, token)
    mediator_client.set_current_agent(agent_name, token)


if __name__ == "__main__":

    socketio.run(app, port=3000)
