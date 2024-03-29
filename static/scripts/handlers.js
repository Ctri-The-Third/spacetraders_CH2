const socket = io();

// for example, when we receive a "ships-list" event, update the dropdown.
socket.on("list_ships", function (data) {
    console.log("Received list-ships event: " + data);
    var shipList = document.getElementById('list_of_ship_symbols');

    if (!shipList) {
        console.log("No shipList found");
        return;
    }

    shipList.innerHTML = '';
    data.forEach(function (ship) {
        console.log("ship that we found - " + ship)
        var option = document.createElement('option');
        option.text = ship;
        shipList.add(option);
    });
});
socket.on("ship-update", function (data) {
    console.log("Ship update received: " + data);
    //if data is a dict already, assign it to the ship variable. if it's a string, json parse it.
    var ship = (typeof data === 'object') ? data : JSON.parse(data);

    var symbol = ship.symbol;
    // for each parameter, find the matching document ID and update it if it exists


    update_ship_object(symbol, ship);


});

function update_ship_object(prefix, ship) {

    // inventory wrapper 
    wrapper = document.getElementById(prefix + "_cargo_inventory");
    if (wrapper) {
        wrapper.innerHTML = '';
        for (key in ship.cargo.inventory) {
            good = ship.cargo.inventory[key];
            console.log(good)
            for (key in good) {
                console.log(key + " " + good[key])
            }

            // add a the key, the units, and a button to sell
            /*
    {{c.symbol}}: {{c.units}} <input type="button" value="sell"
    onclick="socket.emit('sell', {'ship_name':'{{ship.symbol}}', 'good':'{{c.symbol}}', 'quantity':'{{c.units}}'})" />
    
    */

            var newDiv = document.createElement("div");
            newDiv.innerHTML = good.symbol + ": " + good.units + " <input type='button' value='sell' onclick='socket.emit(\"sell\", {\"ship_name\":\"" + ship.symbol + "\", \"good\":\"" + good.symbol + "\"})' />";
            wrapper.appendChild(newDiv);

        }
    }
    rec_update_ship_object(prefix, ship);

    waypoint = document.getElementById(prefix + "_nav_waypointSymbol");
    if (waypoint) {
        waypoint.innerHTML = "<a href = 'waypoints/" + ship.nav.waypointSymbol + "'>" + ship.nav.waypointSymbol + "</a>";
    }
}
function rec_update_ship_object(prefix, ship_piece) {
    // for each parameter, find the matching document ID and update it if it exists
    for (var key in ship_piece) {
        var new_data = ship_piece[key];
        if (typeof new_data === 'object') {
            rec_update_ship_object(prefix + "_" + key, new_data);
        }
        else {
            //console.log("Searching for " + prefix + "_" + key + " to update with " + ship_piece[key])
            var element = document.getElementById(prefix + "_" + key);

            if (element) {
                element.innerHTML = ship_piece[key];
                console.log("Success!")
            }
        }
    }
}
socket.on("market-update", function (data) {

    console.log("Market update received: " + data);
    //if data is a dict already, assign it to the ship variable. if it's a string, json parse it.
    var market = (typeof data === 'object') ? data : JSON.parse(data);


    // whilst the listings are a list, we want them to be a dict with the key being the symbol.
    // this will make it easier to update outputs since we're using keys not indexes.
    listings = market.tradeGoods;
    new_listings = {};
    listings.forEach(function (listing) {
        new_listings[listing.symbol] = listing;

    });
    market.tradeGoods = new_listings;


    imports = market.imports;
    new_imports = {};
    imports.forEach(function (imported) {
        new_imports[imported.symbol] = imported;
    });
    market.imports = new_imports;

    market_exports = market.exports;
    new_exports = {};
    market_exports.forEach(function (exported) {
        new_exports[exported.symbol] = exported;
    });
    market.exports = new_exports;


    new_exchange = {};
    market.exchange.forEach(function (exchanged) {
        new_exchange[exchanged.symbol] = exchanged;
    });
    market.exchange = new_exchange;

    var symbol = market.symbol;
    var market_output = document.getElementById("mkt_" + symbol);
    if (market_output) {
        console.log("Updating market output for " + symbol + " in specific div");
        prefix = "mkt_" + symbol;
    }
    else {
        console.log("Updating market output for market in default div");
        prefix = "market_output";
    }
    console.log(market)
    update_market_object(prefix, market);
    // for each parameter, find the matching document ID and update it if it exists
});
function update_market_object(prefix, market) {

    element = document.getElementById(prefix + "_symbol")
    if (element) { element.innerHTML = market.symbol };
    button = document.getElementById(prefix + "_refresh_button")
    if (button) { button.setAttribute("onclick", "socket.emit('fetch-market', '" + market.symbol + "')"); }

    // -- IMPORTS --
    let content = '';
    for (tradegood in market.imports) {
        //the target div needs to be a list of tradegoods in the form
        //<img src="/static/icons/GOOD_MICROPROCESSORS.png"/> MICROPROCESSORS,

        content += `<img src="/static/icons/GOOD_${tradegood}.PNG"/> ${tradegood}, `;
    }
    //remove the trailing comma
    content = content.slice(0, -2);
    element = document.getElementById(prefix + "_imports")
    if (element) { element.innerHTML = content; }

    // -- EXPORTS --
    content = '';
    for (tradegood in market.exports) {
        content += `<img src="/static/icons/GOOD_${tradegood}.PNG"/> ${tradegood}, `;

    }
    content = content.slice(0, -2);
    element = document.getElementById(prefix + "_exports")
    if (element) { element.innerHTML = content; }

    // -- EXCHANGE --
    content = '';
    for (tradegood in market.exchange) {
        content += `<img src="/static/icons/GOOD_${tradegood}.PNG"/> ${tradegood}, `;

    }
    content = content.slice(0, -2);
    element = document.getElementById(prefix + "_exchange")
    if (element) { element.innerHTML = content; }


    for (var key in market.tradeGoods) {
        // supply, activity, tradeVolume, purchasePrice, sellPrice
        element = document.getElementById(prefix + "_listing_" + key + "_supply_img")
        if (element) { element.src = "/static/icons/" + market.tradeGoods[key].supply + ".PNG" }

        element = document.getElementById(prefix + "_listing_" + key + "_supply")
        if (element) { element.innerHTML = market.tradeGoods[key].supply }

        element = document.getElementById(prefix + "_listing_" + key + "_activity_img")
        if (element) { element.src = "/static/icons/" + market.tradeGoods[key].activity + ".PNG" }

        element = document.getElementById(prefix + "_listing_" + key + "_activity")
        if (element) { element.innerHTML = market.tradeGoods[key].activity }

        element = document.getElementById(prefix + "_listing_" + key + "_tradeVolume")
        if (element) { element.innerHTML = market.tradeGoods[key].tradeVolume }

        element = document.getElementById(prefix + "_listing_" + key + "_purchasePrice")
        if (element) { element.innerHTML = market.tradeGoods[key].purchasePrice }

        element = document.getElementById(prefix + "_listing_" + key + "_sellPrice")
        if (element) { element.innerHTML = market.tradeGoods[key].sellPrice }
    }
    //<input type="button" value="buy max" onclick="socket.emit('buy', {'ship_name':'CTRI-W3-1', 'good':'POLYNUCLEOTIDES'})">
    //<input type="button" value="buy MAX" onclick="socket.emit(" buy',="" {'ship_name':'ctri-w3-1',="" 'good':'fuel})'="">

}

socket.on("agent_update", function (data) {
    console.log("Agent update received: " + data);
    //if data is a dict already, assign it to the ship variable. if it's a string, json parse it.
    var agent = (typeof data === 'object') ? data : JSON.parse(data);
    var symbol = agent.symbol;
    // for each parameter, find the matching document ID and update it if it exists

    var agent_out = document.getElementById("agent_" + symbol);
    if (agent_out) {
        console.log("Updating agent output for " + symbol + " in specific div");
        prefix = "agent_" + symbol;
    }
    else {
        console.log("updating agent output  in default div");
        prefix = "agent_output";
    }

    update_agent_object(prefix, agent);
});
function update_agent_object(prefix, agent) {
    // for each parameter, find the matching document ID and update it if it exists

    for (var key in agent) {

        var element = document.getElementById(prefix + "_" + key);
        if (element) {
            element.innerHTML = agent[key];
        }

    }
}

socket.on("logs-response", function (data) {
    console.log("logs-response: " + data);
    log_output(data);
});

socket.on("message", function (data) {
    console.log("message: " + data);
    log_output(data);
});

function log_output(content) {
    logs_output = document.getElementById('logs_output');
    if (!logs_output) {
        console.log("No logs_output found");
        return;
    }


    logs_output.innerHTML += content + "<br/>";
    logs_output.scrollTop = logs_output.scrollHeight;

}

socket.on("ship-box", function (data) {
    document.getElementById('selected_ship').innerHTML = data;
});




// This function finds all divs with the class 'timer', and sets up an interval.
function initializeTimers() {
    // Find all timer divs

    // Set up an interval that runs every 1000ms (1 second)
    setInterval(function () {
        var timers = document.querySelectorAll('.timer');

        timers.forEach(function (timer) {
            // Get the current value as an integer
            var currentValue = parseInt(timer.textContent, 10);

            // Only decrease the value if it's above 0
            if (currentValue > 0) {
                timer.textContent = currentValue - 1;
            }
        });
    }, 1000);
}

// Call the function when the window loads
window.onload = initializeTimers;