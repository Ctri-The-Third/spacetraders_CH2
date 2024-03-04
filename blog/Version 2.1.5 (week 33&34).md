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
* render trade panel updates to the UI 
* feed markets into trade manager and recalculate those trades only
* when executing manually, detract from available trade value
* auto-trade slider
* Containerise the app
  * ✅ get the app into a docker container
  * ✅ get the app running and talking to the DB
  * ✅ figure out SSH forwarding of the relevant port
  * Get the app to run on a production server not the default

Milestone 4:
* Buy ships from UI 
* ✅ ships view
 
Goals we didn't know we had
* ✅ Restructure the SDK so that clients, models, and responses are all in their own sub-packages, instead of spread out as they are presently.
* ✅ Fix the market object so that it properly renders the tradegoods that aren't listings.
* ✅ On buying goods, the ships don't seem to update in the DB.



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