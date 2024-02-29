const socket = io();

// for example, when we receive a "ships-list" event, update the dropdown.
socket.on("list-ships", function (data) {
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
socket.on("ship_update", function (data) {
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
    rec_update_ship_object(prefix, ship);
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
socket.on("market_update", function (data) {
    console.log("Market update received: " + data);
    //if data is a dict already, assign it to the ship variable. if it's a string, json parse it.
    var market = (typeof data === 'object') ? data : JSON.parse(data);


    // whilst the listings are a list, we want them to be a dict with the key being the symbol.
    // this will make it easier to update outputs since we're using keys not indexes.
    listings = market.tradeGoods;
    new_listings = {};
    listings.forEach(function (listing) {
        new_listings[listing.symbol] = listing;
        console.log("listing: " + listing.symbol + " " + listing.type + " " + listing.supply + " " + listing.activity + " " + listing.purchasePrice + " " + listing.sellPrice)
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

    document.getElementById(prefix + "_symbol").innerHTML = market.symbol;
    button = document.getElementById(prefix + "_refresh_button")
    button.setAttribute("onclick", "socket.emit('fetch-market', '" + market.symbol + "')");

    // -- IMPORTS --
    let content = '';
    for (tradegood in market.imports) {
        //the target div needs to be a list of tradegoods in the form
        //<img src="/static/icons/GOOD_MICROPROCESSORS.png"/> MICROPROCESSORS,

        content += `<img src="/static/icons/GOOD_${tradegood}.PNG"/> ${tradegood}, `;
    }
    //remove the trailing comma
    content = content.slice(0, -2);
    document.getElementById(prefix + "_imports").innerHTML = content;

    // -- EXPORTS --
    content = '';
    for (tradegood in market.exports) {
        content += `<img src="/static/icons/GOOD_${tradegood}.PNG"/> ${tradegood}, `;

    }
    content = content.slice(0, -2);
    document.getElementById(prefix + "_exports").innerHTML = content;

    // -- EXCHANGE --
    content = '';
    for (tradegood in market.exchange) {
        content += `<img src="/static/icons/GOOD_${tradegood}.PNG"/> ${tradegood}, `;

    }
    content = content.slice(0, -2);
    document.getElementById(prefix + "_exchange").innerHTML = content;

    table = document.getElementById(prefix + "_tradeGoods");
    table.innerHTML = '';

    var newRow = table.insertRow(-1);
    newCell = document.createElement("th");
    newCell.textContent = "Good";
    newRow.appendChild(newCell);

    newCell = document.createElement("th");
    newCell.textContent = "Status";
    newRow.appendChild(newCell);

    newCell = document.createElement("th");
    newCell.textContent = "Prices";
    newRow.appendChild(newCell);

    newCell = document.createElement("th");
    newCell.textContent = "Actions";
    newRow.appendChild(newCell);


    for (var key in market.tradeGoods) {
        tg = market.tradeGoods[key];
        var newRow = table.insertRow();
        var newCell = newRow.insertCell(0);
        newCell.textContent = key;

        var newCell = newRow.insertCell(1);
        text_content = "<img src='/static/icons/" + tg.type + ".png'/>";
        text_content += "<img src='/static/icons/" + tg.supply + ".png'/>";
        if (tg.type != "EXCHANGE") { text_content += "<img src='/static/icons/" + tg.activity + ".png'/>" };
        newCell.innerHTML = text_content;

        var newCell = newRow.insertCell(2);
        if (tg.type === "EXPORT") {
            text_content = "buy for : " + tg.purchasePrice;
        }
        else if (tg.type === "IMPORT") {
            text_content = "sell for : " + tg.sellPrice;
        }
        else if (tg.type === "EXCHANGE") {
            text_content = "buy/sell for : " + tg.purchasePrice + "/" + tg.sellPrice;
        }
        newCell.textContent = text_content;

        var newCell = newRow.insertCell(3);

        active_ship = document.getElementById('active_ship');
        if (!active_ship) {

            return;
        }

        emit_instruction = 'socket.emit(\"buy\", {\"ship_name\":\"' + active_ship.value + '\", \"good\":\"' + key + '\", \"quantity\":' + tg.tradeVolume + '})';
        inner_html = "<input type = 'button' value = 'buy" + tg.tradeVolume + "' onclick='" + emit_instruction + "'/> ";

        emit_instruction = 'socket.emit(\"buy\", {\"ship_name\":\"' + active_ship.value + '\", \"good\":\"' + key + '\"})';
        inner_html += "<input type = 'button' value = 'buy max' onclick='" + emit_instruction + "'/>";
        newCell.innerHTML = inner_html;


        //<input type="button" value="buy max" onclick="socket.emit('buy', {'ship_name':'CTRI-W3-1', 'good':'POLYNUCLEOTIDES'})">
        //<input type="button" value="buy MAX" onclick="socket.emit(" buy',="" {'ship_name':'ctri-w3-1',="" 'good':'fuel})'="">

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


socket.on("ship-update", function (data) {
    ship = JSON.parse(data);
    symbol = ship.symbol;

    var shipList = document.getElementById('list_of_ship_symbols');
    if (!shipList) {
        console.log("No shipList found");
        return;
    }
    shipList.value = data;
})



// This function finds all divs with the class 'timer', and sets up an interval.
function initializeTimers() {
    // Find all timer divs
    var timers = document.querySelectorAll('.timer');

    // Set up an interval that runs every 1000ms (1 second)
    setInterval(function () {
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