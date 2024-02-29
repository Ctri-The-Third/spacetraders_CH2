# Week 33/34

We've archived all our previous work, and are starting afresh using the SDK as our foundation - though without being afraid to rework it substantially.  

This time we're starting UI / manual control first.  
Milestone 1:   
* ✅ Login with token / register user 
* ✅ Set up a websocket that returns all logging info to the users.
* ✅ Create a UI that lets you ✅ move / ✅ buy / ✅ sell

Milestone 2:  
* ✅ update cargo on the UI automatically
* list all possible tasks in system
* single click to execute a trade

 
Goals we didn't know we had
* ✅ Restructure the SDK so that clients, models, and responses are all in their own sub-packages, instead of spread out as they are presently.
* ✅ Fix the market object so that it properly renders the tradegoods that aren't listings.
* On buying goods, the ships don't seem to update in the DB.