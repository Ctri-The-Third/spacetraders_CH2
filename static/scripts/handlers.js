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

socket.on("logs-response", function (data) {
    console.log("logs-response: " + data);
    log_output(data);
});

socket.on("message", function (data) {
    console.log("message: " + data);
    log_output(data);
});

function log_output(content) {
    console.log("DBG: Reached as far as log_output")
    logs_output = document.getElementById('logs_output');


    //limit it to just the last 5 lines
    var lines = logs_output.innerHTML.split('<br/>');
    lines.push(content);
    if (lines.length > 5) {
        lines = lines.slice(-5);
    }
    logs_output.innerHTML = lines.join('<br/>');

}