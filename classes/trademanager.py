from straders_sdk.clients import SpaceTradersMediatorClient
import straders_sdk.models as st_models
import straders_sdk.pathfinder as st_pathfinder
import straders_sdk.constants as st_const
import straders_sdk.utils as st_utils
import time, math, threading, json


class TradeOpportunity:
    def __init__(
        self,
        client: SpaceTradersMediatorClient,
        export_tradegood: "TradeGood",
        destination_tradegood: list["TradeGood"],
        selected_destination: str = None,
        strategy="MANAGE",
    ):
        """An export/ exchange, and any matching destinations.
        The mode determines how the traders should interact with the opportunity
        * SKIM: if we're in abaundant, 2* TV
        * SKIP: Nothing to do
        * MANAGE: If weak/growing, trade until LIMITED. If strong, trade until MODERATE.
        """

        self.strategy = strategy
        self.client = client
        self.start_good = export_tradegood
        self.start_location = export_tradegood.waypoint

        self.possible_end_goods = destination_tradegood
        self.selected_end_good = None
        self.trade_symbol = export_tradegood.symbol
        self._pathfinder = st_pathfinder.PathFinder(client)

        self.end_location = None
        self.distance = 0
        self.profit_per_unit = 0
        self.total_quantity = 0
        self.export_tv = self.start_good.trade_volume
        self.goods_produced_per_hour = 0
        self.current_profit_ptrip_pvolume_phour = 0

        self.activity_modifiers = {
            "RESTRICTED": 0.5,
            "WEAK": 1,
            "GROWING": 1.5,
            "STRONG": 2,
            "UNKNOWN": 0.5,
        }
        if selected_destination:
            self.select_destination(selected_destination)
        else:
            self.select_closest_destination()

        if not self.selected_end_good:
            self.strategy = "SKIP"

    def __repr__(self) -> str:
        return f"{self.trade_symbol}: {self.start_location.symbol} -> {self.end_location.symbol}"

    def to_dict(self) -> dict:

        out_obj = {
            "trade_symbol": self.trade_symbol,
            "start_location": self.start_location.symbol,
            # "end_location": self.end_location.symbol,
            "possible_end_locations": [
                x.waypoint.symbol for x in self.possible_end_goods
            ],
            "distance": math.ceil(self.distance),
            "profit_per_unit": self.profit_per_unit,
            "total_quantity": self.total_quantity,
            "supply": self.start_good.supply,
            "activity": self.start_good.activity,
            "export_tv": self.export_tv,
            "scanned_start": self.start_good.buy_price != 0,
            "goods_produced_per_hour": self.goods_produced_per_hour,
            "profit_per_unit_per_distance": round(
                self.profit_per_unit / max(self.distance, 1), 2
            ),
            "strategy": self.strategy,
        }
        if self.end_location:
            out_obj["end_location"] = self.end_location.symbol
            out_obj["scanned_end"] = self.selected_end_good.sell_price != 0
        else:
            out_obj["end_location"] = ""
            out_obj["scanned_end"] = False
        return out_obj

    def select_destination(self, destination_symbol: str):
        for good in self.possible_end_goods:
            if good.waypoint.symbol == destination_symbol:
                self.selected_end_good = good
                self.end_location = good.waypoint
                return

    def select_closest_destination(self):
        # self._pathfinder.calc_distance_between(self.start_location, self.end_location)
        if not self.possible_end_goods:
            return
        closest = self.possible_end_goods[0]
        best_distance = float("inf")
        for good in self.possible_end_goods:
            distance = self._pathfinder.calc_distance_between(
                self.start_location, good.waypoint
            )
            if distance < best_distance:
                best_distance = distance
                closest = good
        self.selected_end_good = closest
        self.end_location = closest.waypoint

    def set_additional_properties(self):
        if not self.selected_end_good:
            return

        self.export_tv = self.start_good.trade_volume
        self.end_location = self.selected_end_good.waypoint
        self.goods_produced_per_hour = (
            self.activity_modifiers[self.start_good.activity]
            * self.start_good.trade_volume
        )
        self.distance = self._pathfinder.calc_distance_between(
            self.start_location, self.end_location
        )
        self.update_prices()

    def calculate_and_set_quantity(self):

        "Should be called either on init, or when we receive a market update with new SUPPLY information"

        if self.strategy == "MANAGE" and self.start_good.activity != "STRONG":
            supplies = {
                "ABUNDANT": 5,  # at minimum 1, at max 5?
                "HIGH": 3,  # got 2 this time
                "MODERATE": 1,  # got 4 this time
                "LIMITED": 0,
                "SCARCE": 0,
                "UNKNOWN": 1,
            }
        elif self.strategy == "MANAGE":
            supplies = {
                "ABUNDANT": 5,
                "HIGH": 1,
                "MODERATE": 0,
                "LIMITED": 0,
                "SCARCE": 0,
                "UNKNOWN": 1,
            }
        elif self.strategy == "SKIM":
            supplies = {
                "ABUNDANT": 1,
                "HIGH": 0,
                "MODERATE": 0,
                "LIMITED": 0,
                "SCARCE": 0,
                "UNKNOWN": 1,
            }
        elif self.strategy == "SKIP":
            supplies = {
                "ABUNDANT": 0,
                "HIGH": 0,
                "MODERATE": 0,
                "LIMITED": 0,
                "SCARCE": 0,
                "UNKNOWN": 0,
            }

        self.total_quantity = (
            self.start_good.trade_volume * supplies[self.start_good.supply]
        )

    def update_prices(self):
        if not self.selected_end_good:
            return
        if not self.selected_end_good.sell_price or not self.start_good.buy_price:
            self.profit_per_unit = 0
        else:
            self.profit_per_unit = (
                self.selected_end_good.sell_price - self.start_good.buy_price
            )

        self.current_profit_ptrip_pvolume_phour = (
            self.profit_per_unit * self.total_quantity / max(self.distance, 1)
        )


class TradeManager:

    def __new__(cls, client: SpaceTradersMediatorClient):
        if not hasattr(cls, "instance"):
            cls.instance = super(TradeManager, cls).__new__(cls)
        return cls.instance

    def __init__(self, client: SpaceTradersMediatorClient):
        if hasattr(self, "client"):
            return
        self.client = client
        agent = client.view_my_self()
        hq = agent.headquarters
        self._pathfinder = st_pathfinder.PathFinder(client)
        self.populate_opportunities()
        self.load_opportunities()
        self.update_opportunities()
        self._refresh_t = threading.Thread(target=self._refresh_quarterly, daemon=True)
        self._refresh_t.start()

    def populate_opportunities(self):
        """Get all markets in listed systems, then get all tradegoods, then match EXPORTS to IMPORTS and EXCHANGES and score."""
        self.opportunities = {}
        client = self.client
        agent = client.view_my_self()
        hq = agent.headquarters
        hq_sys = client.systems_view_one(st_utils.waypoint_to_system(hq))
        waypoints = client.waypoints_view(hq_sys.symbol)
        opportunities = {}
        for waypoint in waypoints.values():
            if (
                waypoint.type not in ("ASTEROID", "GAS_GIANT")
                and len(waypoint.traits) == 0
            ):
                client.waypoints_view_one(waypoint.symbol, True)

        systems = {hq_sys.symbol: {}}
        for system in systems:
            opportunities[system] = []
            waypoints = self.client.find_waypoints_by_trait(
                hq_sys.symbol, "MARKETPLACE"
            )
            systems[system] = goods_list = {}
            for waypoint in waypoints:
                market = self.client.system_market(waypoint)
                if market.is_stale(30):
                    new_market = self.client.system_market(waypoint, True)
                    if len(new_market.listings) != 0:
                        market = new_market
                for good in market.imports:
                    if good.symbol not in goods_list:
                        goods_list[good.symbol] = []
                    goods_list[good.symbol].append(
                        TradeGood(
                            waypoint,
                            good,
                            "IMPORT",
                            market.get_tradegood_listing(good.symbol),
                        )
                    )
                for good in market.exports:
                    if good.symbol not in goods_list:
                        goods_list[good.symbol] = []
                    tg = market.get_tradegood_listing(good.symbol)
                    goods_list[good.symbol].append(
                        TradeGood(
                            waypoint,
                            good,
                            "EXPORT",
                            market.get_tradegood_listing(good.symbol),
                        )
                    )
                for good in market.exchange:
                    if good.symbol not in goods_list:
                        goods_list[good.symbol] = []
                    tg = market.get_tradegood_listing(good.symbol)
                    goods_list[good.symbol].append(
                        TradeGood(
                            waypoint,
                            good,
                            "EXCHANGE",
                            market.get_tradegood_listing(good.symbol),
                        )
                    )

        for system_symbol, system in systems.items():
            for tg_symbol, goods_list in system.items():
                goods_list
                exports = [x for x in goods_list if x.type in "EXPORT"]
                imports = [x for x in goods_list if x.type in ["IMPORT", "EXCHANGE"]]

                for export in exports:

                    opportunities[system_symbol].append(
                        TradeOpportunity(self.client, export, imports)
                    )
        self.opportunities = opportunities

    def update_opportunities(self):
        "When should this be called?"
        for system, opportunities in self.opportunities.items():
            for opportunity in opportunities:
                opportunity: TradeOpportunity
                opportunity.set_additional_properties()
                opportunity.calculate_and_set_quantity()

    def update_market(self, market: st_models.Market):
        "receives a market object, and updates all opportunities associated with it"
        system = st_utils.waypoint_to_system(market.symbol)

        for opportunity in self.opportunities.get(system, []):
            opportunity: TradeOpportunity
            matching_tg = market.get_tradegood(opportunity.trade_symbol)
            matching_tgl = market.get_tradegood_listing(opportunity.trade_symbol)
            if not matching_tg:
                continue

            if opportunity.start_location.symbol == market.symbol:
                opportunity.start_good = TradeGood(
                    opportunity.start_location, matching_tg, "EXPORT", matching_tgl
                )
                opportunity.set_additional_properties()
                opportunity.calculate_and_set_quantity()
            else:
                for end_good in opportunity.possible_end_goods:
                    if end_good.waypoint.symbol == market.symbol:
                        end_good = TradeGood(
                            end_good.waypoint, matching_tg, end_good.type, matching_tgl
                        )

                        opportunity.update_prices()
                        break

    def load_opportunities(self):
        "load the opportunities selected destination, and their strategy, from file"
        try:
            with open("resources/opportunities.json", "r") as f:
                data = f.read()

                for system, opps in json.loads(data).items():
                    for opp_j in opps:
                        opp_j: dict
                        matched_o = self.find_opportunity(system, opp_j["trade_symbol"])
                        matched_o: TradeOpportunity
                        if not matched_o:
                            continue

                        selected_destination = opp_j.get("end_location", None)
                        if selected_destination:
                            matched_o.select_destination(selected_destination)

                            strategy = opp_j.get("strategy", "MANAGE")
                        else:
                            strategy = opp_j.get("strategy", "SKIP")
                        matched_o.strategy = strategy
        except FileNotFoundError:
            self.save_opportunities()

    def update_strategy(
        self, system_symbol: str, trade_symbol: str, end_location: str, strategy: str
    ):
        matched_o = self.find_opportunity(system_symbol, trade_symbol)
        if not matched_o:
            return
        matched_o: TradeOpportunity
        matched_o.select_destination(end_location)
        matched_o.strategy = strategy
        self.save_opportunities()

    def find_opportunity(self, system_str, export_str):
        for opportunity in self.opportunities[system_str]:
            if opportunity.trade_symbol == export_str:
                return opportunity

    def save_opportunities(self):
        "save the opportunities selected destination, and their strategy, to file"
        with open("resources/opportunities.json", "w+") as f:
            f.write(json.dumps(self.list_opportunities_for_json(), indent=2))

    def pick_best_trade(
        self,
        system_symbol: str,
        start_location: str,
        ship_cargo_capacity: int,
        max_distance: int = None,
    ):

        if not max_distance:
            max_distance = float("inf")
        local_opportunities = self.opportunities.get(system_symbol, [])
        start_waypoint = self.client.waypoints_view_one(start_location)
        valid_opportunities = []
        for opportunity in local_opportunities:
            opportunity: TradeOpportunity
            if opportunity.strategy == "SKIP":
                continue
            if opportunity.distance > max_distance:
                continue
            if opportunity.profit_per_unit < 0:
                continue
            if opportunity.total_quantity <= 0:
                continue
            total_distance = (
                self._pathfinder.calc_distance_between(
                    start_waypoint, opportunity.start_location
                )
                + opportunity.distance
            )
            potential_quantity = min(opportunity.total_quantity, ship_cargo_capacity)
            score = (opportunity.profit_per_unit * potential_quantity) / max(
                total_distance, 1
            )
            valid_opportunities.append((score, opportunity))

        valid_opportunities.sort(key=lambda x: x[0], reverse=True)
        if valid_opportunities:
            best_opp = valid_opportunities[0][1]

            return best_opp
        elif max_distance < float("inf"):
            return self.pick_best_trade(
                system_symbol, start_location, ship_cargo_capacity
            )

        # we need to reduce the total quantity by the amount of cargo we have

    def get_opportunity_json(self, system_symbol: str, trade_symbol: str) -> dict:
        for opportunity in self.opportunities.get(system_symbol, []):
            if opportunity.trade_symbol == trade_symbol:
                opportunity: TradeOpportunity

                return_obj = opportunity.to_dict()
                tg = opportunity.start_good
                return_obj["friendly_name"] = tg.name
                return_obj["description"] = tg.description
                return_obj["manufactured_by"] = st_const.MANUFACTURED_BY.get(
                    tg.symbol, []
                )
                return_obj["manufactures"] = st_const.MANUFACTURES.get(tg.symbol, [])
                return_obj["possible_locations"] = {}
                return_obj["scanned_start_b"] = tg.buy_price != 0
                return_obj["scanned_end_b"] = (
                    opportunity.selected_end_good.sell_price != 0
                )
                for end_good in opportunity.possible_end_goods:
                    return_obj["possible_locations"][end_good.waypoint.symbol] = {
                        "sell_price": end_good.sell_price,
                        "distance": self._pathfinder.calc_distance_between(
                            tg.waypoint, end_good.waypoint
                        ),
                        "profit_per_unit": end_good.sell_price - tg.buy_price,
                        "profit_per_distance": (end_good.sell_price - tg.buy_price)
                        / max(opportunity.distance, 1),
                    }

                return return_obj
        return {}

    def _refresh_quarterly(self):
        """Refresh the opportunities every quarter-hour. Note, should be run from a daemon thread."""
        loops = 0
        while True:
            time.sleep(900)
            loops += 1
            # currently we're blindly increasing the quantity - but if we're skimming (for example) then we shouldn't be increasing the quantity unless we're in the right supply state
            # but supply state isn't something we're actively modelling - so this is instead should be a "check on the market"  function instead.
            # for each market we're monitoring - if the strategy is "MANAGE" then we should check every 30 minutes (1 TV)
            # if the strategy is "SKIM" we should check every 2 hours (1 TV at RESTRICTED)
            got_markets = {}
            for system in self.opportunities.values():
                for opp in system:
                    opp: TradeOpportunity
                    export_market = self.get_market(opp.start_location, got_markets)
                    refresh = False
                    export_market: st_models.Market
                    if opp.strategy == "MANAGE":
                        refresh = export_market.is_stale(30)
                    elif opp.strategy == "SKIM":
                        refresh = export_market.is_stale(120)

                    if refresh:
                        export_market = self.get_market(
                            opp.start_location, got_markets, True
                        )

                    for import_market in opp.possible_end_goods:
                        import_market: TradeGood
                        refresh = False
                        import_market = self.get_market(
                            import_market.waypoint, got_markets
                        )
                        import_market: st_models.Market
                        if opp.strategy == "MANAGE":
                            refresh = import_market.is_stale(30)
                        elif opp.strategy == "SKIM":
                            refresh = import_market.is_stale(120)

                        if refresh:
                            wayp = st_models.Waypoint(
                                st_utils.waypoint_to_system(import_market.symbol),
                                import_market.symbol,
                                "",
                                0,
                                0,
                                [],
                                [],
                                [],
                                False,
                                False,
                                [],
                            )
                            import_market = self.get_market(wayp, got_markets, True)

                    opp.update_prices()
                    opp.calculate_and_set_quantity()

    def get_market(
        self, waypoint: st_models.Waypoint, got_markets: dict, refresh: bool = False
    ):
        if waypoint.symbol in got_markets and not refresh:
            return got_markets[waypoint.symbol]
        market = self.client.system_market(waypoint, refresh)
        if len(market.listings) > 0:

            got_markets[waypoint.symbol] = market
        return market

    def list_opportunities(self, system_symbol: str):

        # score = (opportunity.profit_per_unit * potential_quantity) / total_distance
        self.opportunities.get(system_symbol, []).sort(
            key=lambda x: (x.profit_per_unit * x.total_quantity / max(x.distance, 1)),
            reverse=True,
        )
        return self.opportunities.get(system_symbol, [])

    def list_opportunities_for_json(self):
        systems = {}
        for system in self.opportunities:
            systems[system] = []
            for opportunity in self.list_opportunities(system):
                opportunity: TradeOpportunity
                systems[system].append(opportunity.to_dict())
            systems[system].sort(
                key=lambda x: (x["profit_per_unit_per_distance"]),
                reverse=True,
            )
        return systems

    def claim_trade(
        self, trade_symbol: str, start_location: str, end_location: str, quantity: int
    ):
        # we need to go through all the trades finding an export that matches the start, and an import that matches the end
        # then we need to subtract from the quantity
        if isinstance(quantity, str):
            quantity = int(quantity)
        for system, opportunities in self.opportunities.items():
            for opportunity in opportunities:
                opportunity: TradeOpportunity
                if (
                    opportunity.trade_symbol == trade_symbol
                    and opportunity.start_location.symbol == start_location
                    and opportunity.end_location.symbol == end_location
                ):
                    opportunity.total_quantity -= quantity

                    return


class TradeGood(st_models.MarketTradeGoodListing):
    def __init__(
        self,
        location: st_models.Waypoint,
        tradegood: st_models.MarketTradeGood,
        type: str,
        tradegood_listing: st_models.MarketTradeGoodListing = None,
    ):
        if isinstance(tradegood_listing, st_models.MarketTradeGood):
            tradegood_listing = None

        self.symbol = tradegood.symbol
        self.name = tradegood.name
        self.description = tradegood.description
        self.waypoint = location
        self.type = type
        self.trade_volume = tradegood_listing.trade_volume if tradegood_listing else 0
        self.activity = tradegood_listing.activity if tradegood_listing else "UNKNOWN"
        self.supply = tradegood_listing.supply if tradegood_listing else "UNKNOWN"
        self.buy_price = tradegood_listing.purchase_price if tradegood_listing else 0
        self.sell_price = tradegood_listing.sell_price if tradegood_listing else 0

    def __repr__(self) -> str:
        return f"{self.symbol}: {self.type} ({self.supply}, {self.activity})"


if __name__ == "__main__":
    import os

    ST_HOST = os.environ.get("ST_DB_HOST", "localhost")
    ST_NAME = os.environ.get("ST_DB_NAME", "spacetraders")
    ST_USER = os.environ.get("ST_DB_USER", "spacetraders")
    ST_PASS = os.environ.get("ST_DB_PASS", "spacetraders")
    ST_PORT = os.environ.get("ST_DB_PORT", "5432")

    with open("token.secret", "r") as f:
        token = f.read()

    client = SpaceTradersMediatorClient(
        token,
        db_host=ST_HOST,
        db_name=ST_NAME,
        db_user=ST_USER,
        db_pass=ST_PASS,
        db_port=ST_PORT,
    )
    # why is X1-SZ74-A4's Advanced Circuitry rocking up as an EXPORT instead of the accurate IMPORT?
    #
    #
    tm = TradeManager(client)
    tm.load_opportunities()
    opps = tm.list_opportunities("X1-SZ74")
    tm.save_opportunities()
