from straders_sdk.clients import SpaceTradersMediatorClient
import straders_sdk.models as st_models
import straders_sdk.pathfinder as st_pathfinder
import straders_sdk.constants as st_const
import straders_sdk.utils as st_utils
import time, math, threading


class TradeOpportunity:
    def __init__(
        self,
        client: SpaceTradersMediatorClient,
        export_tradegood: "TradeGood",
        destination_tradegood: "TradeGood",
    ):

        self.client = client
        self.start_good = export_tradegood
        self.start_location = export_tradegood.waypoint

        self.end_good = destination_tradegood
        self.end_location = destination_tradegood.waypoint

        self.trade_symbol = export_tradegood.symbol
        self._pathfinder = st_pathfinder.PathFinder(client)
        self.distance = self._pathfinder.calc_distance_between(
            self.start_location, self.end_location
        )
        activity_mod = {
            "RESTRICTED": 0.5,
            "WEAK": 1,
            "GROWING": 1.5,
            "STRONG": 2,
            "UNKNOWN": 999,
        }
        supplies = {
            "ABUNDANT": 2 + 4,
            "HIGH": 4,
            "MODERATE": 0,
            "LIMITED": 0,
            "SCARCE": 0,
        }
        demands = {
            "SCARCE": 16 + 8 + 8 + 4 + 2,
            "LIMITED": 8 + 8 + 4 + 2,
            "MODERATE": 8 + 4 + 2,
            "HIGH": 4,
            "ABUNDANT": 2,
        }
        self.distance = self._pathfinder.calc_distance_between(
            self.start_location, self.end_location
        )
        self.profit_per_unit = self.end_good.sell_price - self.start_good.buy_price

        if not self.start_good.buy_price:
            supply_quantity = 18
        else:
            supply_quantity = (
                supplies[self.start_good.supply] * self.start_good.trade_volume
            )

        if not self.end_good.sell_price:
            demand_quantity = 18
        else:
            demand_quantity = demands[self.end_good.supply] * self.end_good.trade_volume

        self.total_quantity = min(supply_quantity, demand_quantity)
        self.export_tv = self.start_good.trade_volume
        self.goods_produced_per_hour = (
            self.start_good.trade_volume * activity_mod[self.start_good.activity]
        )
        # profit per trip
        self.current_profit_ptrip_pvolume_phour = (
            self.profit_per_unit / self.distance * self.export_tv
        ) * activity_mod[self.start_good.activity]

    def __repr__(self) -> str:
        return f"{self.trade_symbol}: {self.start_location.symbol} -> {self.end_location.symbol}"

    def to_dict(self) -> dict:
        return {
            "start_location": self.start_location.symbol,
            "end_location": self.end_location.symbol,
            "trade_symbol": self.trade_symbol,
            "distance": math.ceil(self.distance),
            "profit_per_unit": self.profit_per_unit,
            "total_quantity": self.total_quantity,
            "export_tv": self.export_tv,
            "goods_produced_per_hour": self.goods_produced_per_hour,
            "cph_of_goods_produced": round(self.current_profit_ptrip_pvolume_phour, 2),
        }


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
            if "ASTEROID" not in waypoint.type and len(waypoint.traits) == 0:
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
                for good in market.imports:
                    if good.symbol not in goods_list:
                        goods_list[good.symbol] = []
                    goods_list[good.symbol].append(
                        TradeGood(
                            waypoint, good, "IMPORT", market.get_tradegood(good.symbol)
                        )
                    )
                for good in market.exports:
                    if good.symbol not in goods_list:
                        goods_list[good.symbol] = []
                    tg = market.get_tradegood(good.symbol)
                    goods_list[good.symbol].append(
                        TradeGood(
                            waypoint, good, "EXPORT", market.get_tradegood(good.symbol)
                        )
                    )
                for good in market.exchange:
                    if good.symbol not in goods_list:
                        goods_list[good.symbol] = []
                    tg = market.get_tradegood(good.symbol)
                    goods_list[good.symbol].append(
                        TradeGood(
                            waypoint,
                            good,
                            "EXCHANGE",
                            market.get_tradegood(good.symbol),
                        )
                    )
        for system_symbol, system in systems.items():
            for tg_symbol, goods_list in system.items():
                goods_list
                exports = [x for x in goods_list if x.type in "EXPORT"]
                imports = [x for x in goods_list if x.type in ["IMPORT", "EXCHANGE"]]

                for export in exports:
                    for imp in imports:

                        opportunities[system_symbol].append(
                            TradeOpportunity(self.client, export, imp)
                        )
        self.opportunities = opportunities

    def claim_best_trade(
        self,
        system_symbol: str,
        start_location: str,
        max_distance: int,
        ship_cargo_capacity: int,
    ):

        local_opportunities = self.opportunities.get(system_symbol, [])
        start_waypoint = self.client.waypoints_view_one(start_location)
        valid_opportunities = []
        for opportunity in local_opportunities:
            if opportunity.distance > max_distance:
                continue
            total_distance = (
                self._pathfinder.calc_distance_between(
                    start_waypoint, opportunity.start_location
                )
                + opportunity.distance
            )
            potential_quantity = min(opportunity.total_quantity, ship_cargo_capacity)
            score = (opportunity.profit_per_unit * potential_quantity) / total_distance
            valid_opportunities.append((score, opportunity))

        valid_opportunities.sort(key=lambda x: x[0], reverse=True)
        if valid_opportunities:
            best_opp = valid_opportunities[0][1]

            self.opportunities[system_symbol].remove(best_opp)
            best_opp.total_quantity -= ship_cargo_capacity
            self.opportunities[system_symbol].append(best_opp)
            return best_opp

        # we need to reduce the total quantity by the amount of cargo we have

    def _refresh_quarterly(self):
        """Refresh the opportunities every quarter-hour. Note, should be run from a daemon thread."""
        loops = 0
        while True:
            time.sleep(900)
            loops += 1
            if loops % 4 == 0:
                # re-fetch markets and rebuild opportunities
                self.populate_opportunities()
                loops = 0
            else:
                for system in self.opportunities.values():
                    for opp in system:
                        opp: TradeOpportunity
                        if opp.start_good.supply != "ABUNDANT":
                            opp.total_quantity += opp.goods_produced_per_hour / 4

    def list_opportunities(self, system_symbol: str):

        # score = (opportunity.profit_per_unit * potential_quantity) / total_distance
        self.opportunities.get(system_symbol, []).sort(
            key=lambda x: (x.profit_per_unit * x.total_quantity / x.distance),
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
        return systems

    def claim_trade(
        self, trade_symbol: str, start_location: str, end_location: str, quantity: int
    ):
        # we need to go through all the trades finding an export that matches the start, and an import that matches the end
        # then we need to subtract from the quantity
        for system, opportunities in self.opportunities.items():
            for opportunity in opportunities:
                opportunity: TradeOpportunity
                if (
                    opportunity.trade_symbol == trade_symbol
                    and opportunity.start_location == start_location
                    and opportunity.end_location == end_location
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
    opportunity = tm.claim_best_trade("X1-SZ74", "X1-SZ74-A1", 400, 40)
    second_opportunity = tm.claim_best_trade("X1-SZ74", "X1-SZ74-A1", 400, 40)
    opps = tm.list_opportunities("X1-SZ74")
    print(opportunity)
