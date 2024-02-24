from flask import Flask, render_template, request, redirect
from functools import wraps
from straders_sdk.clients import SpaceTradersAPIClient

app = Flask("C'tri's SpaceTraders Client")


api_client = SpaceTradersAPIClient()


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


@app.route("/")
@check_login
def index():
    return "Operator, I'm in!"


if __name__ == "__main__":

    app.run()
