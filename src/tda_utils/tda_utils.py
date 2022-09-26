from tda import auth, client
from . import credential as cred
from datetime import datetime
import pytz
import json
import requests
from tda.orders.equities import (
    equity_buy_limit,
    equity_buy_market,
    equity_sell_limit,
    equity_sell_market,
)
import time
import yaml
from datetime import timezone
import os, sys


class tda:
    def __init__(self):
        self.c = auth.client_from_token_file(cred.tda_token_path, cred.tda_api_key)
        self.token_old()

    def market_open(self) -> bool:
        # r = self.c.get_hours_for_single_market(
        #    client.Client.Markets.EQUITY, datetime.now()
        # ).json()
        # return r["equity"]["EQ"]["isOpen"]
        """Get market open with alpaca api"""
        header = {
            "APCA-API-KEY-ID": cred.alpaca_api_key,
            "APCA-API-SECRET-KEY": cred.alpaca_api_secret,
        }
        r = requests.get("https://api.alpaca.markets/v2/clock", headers=header)
        return r.json()["is_open"]

    def token_old(self) -> int:
        timestamp = json.loads(open(cred.tda_token_path, "r").read())[
            "creation_timestamp"
        ]
        token_days = (datetime.now() - datetime.fromtimestamp(timestamp)).days
        if token_days > 89:
            print("Token expired.")
        elif token_days > 60:
            print(f"TD ameritrade token expires in {90 - token_days} days.")

        return token_days

    def get_portfolio(self) -> dict:
        response = self.c.get_account(
            cred.tda_accountid, fields=client.Client.Account.Fields.POSITIONS
        ).json()["securitiesAccount"]
        output = {
            position["instrument"]["symbol"]: int(
                position["longQuantity"] - position["shortQuantity"]
            )
            for position in response["positions"]
        }
        output["USD"] = response["currentBalances"]["availableFunds"]
        output["net"] = response["currentBalances"]["liquidationValue"]
        return output

    def get_recent_order(self) -> dict:
        return self.c.get_orders_by_path(cred.tda_accountid).json()[0]

    def get_order(self, orderid: int) -> dict:
        return self.c.get_order(orderid, cred.tda_accountid).json()

    def get_quote(self, symbol: str) -> dict:
        return self.c.get_quotes(symbol).json()[symbol]

    def get_atr(self, symbol: str) -> float:
        """Returns 1 min atr for the last 5 mins"""
        bars = self.c.get_price_history(
            symbol,
            period_type=client.Client.PriceHistory.PeriodType.DAY,
            period=client.Client.PriceHistory.Period.ONE_DAY,
            frequency_type=client.Client.PriceHistory.FrequencyType.MINUTE,
            frequency=client.Client.PriceHistory.Frequency.EVERY_MINUTE,
            end_datetime=datetime.now(),
        ).json()["candles"][-6:]
        TR = [
            max(bars[ii + 1]["high"], bars[ii]["close"])
            - min(bars[ii + 1]["low"], bars[ii]["close"])
            for ii in range(len(bars) - 1)
        ]
        return sum(TR) / len(TR)

    def get_last_9min_prices(self, symbol: str) -> list:
        r = self.c.get_price_history(
            symbol,
            period_type=client.Client.PriceHistory.PeriodType.DAY,
            period=client.Client.PriceHistory.Period.ONE_DAY,
            frequency_type=client.Client.PriceHistory.FrequencyType.MINUTE,
            frequency=client.Client.PriceHistory.Frequency.EVERY_MINUTE,
            end_datetime=datetime.now(),
        )
        bars = r.json()["candles"][-9:]
        return [bar["close"] for bar in bars]

    def open_position_market(self, symbol: str, quantity: int) -> dict:
        order = self.c.place_order(cred.tda_accountid, equity_buy_market(symbol, quantity))
        return self.get_order(int(order.headers['Location'].split('/')[-1]))

    def open_position_limit(
        self, symbol: str, quantity: int, wait_time: float = 300, slip_allow: float = 0
    ) -> dict:
        order = self.c.place_order(
            cred.tda_accountid,
            equity_buy_limit(
                symbol, quantity, self.get_quote(symbol)["lastPrice"] * (1 + slip_allow)
            ),
        )
        orderid = int(order.headers['Location'].split('/')[-1])
        tic = time.time()
        while (
            self.c.get_order(orderid, cred.tda_accountid).json()["status"] != "FILLED"
        ):
            toc = time.time()
            if toc - tic > wait_time:
                print("Forcing market order ...")
                order = self.c.replace_order(
                    cred.tda_accountid,
                    orderid,
                    equity_buy_market(
                        symbol,
                        self.c.get_order(orderid, cred.tda_accountid).json()[
                            "remainingQuantity"
                        ],
                    ),
                )
                orderid = int(order.headers['Location'].split('/')[-1])
            time.sleep(3)
        return self.get_order(orderid)

    def liquidate_market(self, symbol: str, quantity: int) -> dict:
        order = self.c.place_order(
            cred.tda_accountid,
            equity_sell_market(symbol, quantity),
        )
        return self.get_order(int(order.headers['Location'].split('/')[-1]))

    def liquidate_limit(
        self, symbol: str, quantity: int, wait_time: float = 300, slip_allow: float = 0
    ) -> dict:
        order = self.c.place_order(
            cred.tda_accountid,
            equity_sell_limit(
                symbol,
                quantity,
                self.get_quote(symbol)["lastPrice"] * (1 - slip_allow),
            ),
        )
        orderid = int(order.headers['Location'].split('/')[-1])
        tic = time.time()
        while (
            self.c.get_order(orderid, cred.tda_accountid).json()["status"] != "FILLED"
        ):
            toc = time.time()
            if toc - tic > wait_time:
                print("Forcing market order ...")
                order = self.c.replace_order(
                    cred.tda_accountid,
                    orderid,
                    equity_sell_market(
                        symbol,
                        self.c.get_order(orderid, cred.tda_accountid).json()[
                            "remainingQuantity"
                        ],
                    ),
                )
                orderid = int(order.headers['Location'].split('/')[-1])
            time.sleep(3)

        return self.get_order(orderid)

    def compare_volume(self, symbol: str) -> bool:
        """Compares previous day volume and today volume (9:30 ~ 15:50)"""
        r = self.c.get_price_history(
            symbol,
            period_type=client.Client.PriceHistory.PeriodType.DAY,
            period=client.Client.PriceHistory.Period.TWO_DAYS,
            frequency_type=client.Client.PriceHistory.FrequencyType.MINUTE,
            frequency=client.Client.PriceHistory.Frequency.EVERY_FIVE_MINUTES,
            end_datetime=datetime.now(),
            need_extended_hours_data=False,
        )
        bars = r.json()["candles"]
        vol_list = [bar["volume"] for bar in bars]
        prev_vol = sum(vol_list[:76])
        cur_vol = sum(vol_list[78:154])

        return cur_vol > prev_vol


class log:
    def __init__(self, path: str = os.path.dirname(sys.argv[0])):
        self.path = path
        self.tz = pytz.timezone("US/Eastern") # timezone.utc

    def log(self, message: str) -> None:
        path = f"{self.path}/log.txt"
        lines = open(path, "r").readlines()
        with open(path, "w") as file:
            for line in lines[-99:]:
                file.write(line)
            file.write(
                datetime.now(self.tz).strftime("%Y-%m-%dT%H:%M:%S")
                + " "
                + message
                + "\n"
            )

    def read(self) -> dict:
        path = f"{self.path}/history.yaml"
        return yaml.safe_load(open(path, "r"))[0]

    def record(self, item: dict) -> None:

        item["date"] = datetime.now(self.tz).strftime("%Y-%m-%d")

        path = f"{self.path}/history.yaml"

        history = yaml.safe_load(open(path, "r"))
        history.insert(0, item)
        yaml.dump(history, open(path, "w"))
