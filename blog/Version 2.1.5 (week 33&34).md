# Week 33/34

We've archived all our previous work, and are starting afresh using the SDK as our foundation - though without being afraid to rework it substantially.  

This time we're starting UI / manual control first.  
Milestone 1:   
* ✅ Login with token / register user 
* ✅ Set up a websocket that returns all logging info to the users.
* ✅ Create a UI that lets you ✅ move / ✅ buy / ✅ sell

Milestone 2:  
* ✅ update cargo on the UI automatically
* ✅ list all possible trades in system
* ✅ single click to execute a trade

Milestone 3: 
* ✅ render trade panel updates to the UI 
  * 🤔 for future development, I think I will switch to this approach. Load empty template and request content, so only have to impliment it once instead of twice.
  * 🤔 whilst it's more work, having a page that loads fully instead of flickering, looks better.
* ✅ Be able to assign behaviours to exports. (skim, skip, manage)
  * ✅ manually in the json
  * ✅ with a UI element
* format credit numbers like so: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number/toLocaleString
* ✅ Be able to assign destinations to exports. (Default to most profitable per distance)
  * ✅ manually in the json
  * ✅ with a UI element
* ✅ when executing manually, detract from available trade value

Milestone 4: 
* ✅ Add factions to login page
* ✅ Make a menu bar
* ✅ auto-trade slider
* ✅ ships view
* ✅ Containerise the app
  * ✅ get the app into a docker container
  * ✅ get the app running and talking to the DB
  * ✅ figure out SSH forwarding of the relevant port
  * ✅ Get the app to run on a production server not the default

Milestone 5:
* ✅ Add "force unlock" button to ship panel
* ✅ be able to reach the J trades (multi-hop navigation)
* ☑️ Waypoint panel 
 * Market
 * ☑️ Shipyard
   * ✅ buy ships from UI
   * Fix the refreshing behaviour
 * Construction site
 * present ship dropdown
 * active ship can be set by query param / linked from ship
* Pathfinder works again/ ships avble to navigate.
* Ship list has system filters and role filters
* Bootstrap the ship panel


Milestone 6: 
* Mining site class 
 * has management UI
 * knows what it can export
 * has strategy (disabled, extract_and_chill)
 * has assigned shpips (just extractors)
 * has sell locations (be those exchanges, or imports)
* mining site panel appears on waypoint panel 

Goals we didn't know we had (tech debt)
* ✅ Restructure the SDK so that clients, models, and responses are all in their own sub-packages, instead of spread out as they are presently.
* ✅ Fix the market object so that it properly renders the tradegoods that aren't listings.
* ✅ On buying goods, the ships don't seem to update in the DB.
* ✅ Add orbital support to the SDK


When it comes to trade manager, I think what I want to do is mark ships as assigned to the trade manager. We can then also have an asteroid manager, and have ships assigned to that, down the line.
In terms of identifying which trades to follow through on, a trade should persist based on its start location, end location, and trade symbol.
Currently we calculate trades based on the relation from an export to an import. I want to codify that batter.

Each Export can be flagged as "Skip", "Skim", or "Trade".
* Skipped exports are ignored. 
* Skimmed exports are ones that are only traded whlist ABUNDANT
* Traded exports are traded down to a supply level matching their activity.
  * RESTRICTED - trades are traded down from ABUNDANT, stopping at HIGH
  * WEAK/GROWING - trades are traded until the supply is LIMITED, then stopped.
  * STRONG - trades are traded until the supply is MODERATE.
* Traded exports are also given a number of matching specific import locations that will be used. s



**troubleshooting the trade manager ☑️**

* ❌ When I claimed a trade, the quantities refilled.
* ✅ When I purchased cargo and the supply was still abundant, the quantity refilled
* ❌ When I sold cargo, and the cached supply was still abundant, the quantity refilled.
* ❌ When I press the "get trades again" button, the quantities are refilled.

Quantity is set when we call 'set_additional_properties'
We should only SET quantity arbitrarily on a market upate. 
Note, the "arbitrary quantity" for ABUNDANT = 1 TV, but the growth cap is 2* TV, so it's probable that we'll lose accummulated quantity if we don't consume at least one whole TV per trip.


**Troubleshooting the waypoint list**

Problem:  
The cached system object doesn't have all the waypoint traits that it could - some are missing.  

Solution:  
To solve this, we have replaced the system.waypoints reference with mediator.waypoints_view(system.symbol)


