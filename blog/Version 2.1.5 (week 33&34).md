# Week 33/34

We've archived all our previous work, and are starting afresh using the SDK as our foundation - though without being afraid to rework it substantially.  

This time we're starting UI / manual control first.
Initial goals
* ✅ Login with token / register user 
* ✅ Set up a websocket that returns all logging info to the users.
* ☑️ Create a UI that lets you ✅ move / buy / sell


Goals we didn't know we had
* ✅ Restructure the SDK so that clients, models, and responses are all in their own sub-packages, instead of spread out as they are presently.
* Rework the market_tradegoods to work like shipyard_types - only including price information when supplied and using a singular table otherwise.