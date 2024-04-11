# Patch 2.2.0 (week 35&36)

This fortnight we're introducing damage events and ship condition, which will be very insightful.

Copying over the milestones from last week

Dev Milestone 1:
* ✅ Support for events in the SDK 
* ✅ Support for condition and integrity in the DB
* ✅ Capture engine information in the DB (same as frame)
* ✅ Display condition and integrity in the UI
Gameplay:
* ✅ Deploy probes to key markets
* ✅ Visit all markets once

Milestone 2:
* ☑️ Waypoint panel 
 * ✅ Market
 * ✅ Shipyard
   * ✅ buy ships from UI
   * ✅ Fix the refreshing behaviour
 * Construction site
 * present ship dropdown
 * active ship can be set by url param / linked from ship
* ✅ satelitte indicator
* ✅ Pathfinder works again/ ships avble to navigate.
* Ship list has system filters and role filters
* Bootstrap the ship panel
* ✅ Why are ships failing to complete their processes sometimes?
  * 🩹 When ships refuel, they don't undock sometimes. Is this an issue of state imbalance between the ship object inside the "refuel" method and the one outside?
  * Ships with cargo should be sent to sell what they've got at the best location


Milestone 3: 
* ✅ Mining site class 
 * has management UI
 * ✅ knows what it can export, and where too.
 * Can broadcast available goods to the trade manager
   * 🐛 when we arrive and sell, it's causing the trade manager to do FULL refresh of all unseen markets, as is proper. Need to add in functionality for checking if a ship is present before doing that.
 * ✅ has assigned ships (just extractors)
 * ✅ has sell locations (be those exchanges, or imports)
   * ✅ after selling, the rtb instruction fails wasting a request before the other thread picks it up.
* mining site panel appears on waypoint panel 
* Trade panel shows requisite imports, and potential export destinations


### Downtime investigation

Every time we wake up/ come back to the game after a while, the ship is not in autopilot mode. 
Theory: Something about the hourly tick is causing the entry for the ship to stop
The code doesn't suggest that's happening though.


### ships aren't singletons

But they really should be. A ship with a given symbol should be the same ship everywhere.

The cache should have an internal dict of ship objects that are returned, or populated as necessary.
The "update" method should also update the SDK's ship object.

BUT WAIT there's more - we use multiple instances of the SDK in different places. 
Q. Is this where we talk about generators and yield statements?  
A. No - those are for synthetic loops

Q. Should we make a threadsafe ships and markets cache baked into the SDK so that all markets and ships returned are the same object? Yes. 


### Ship exports without fixed destinations!

currently rendering, but price / profit information not being set.
Also, need to exclude trade opportunities that only EXCHANGE to EXCHANGE trades.