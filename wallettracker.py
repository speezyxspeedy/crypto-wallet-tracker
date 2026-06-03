import urllib.request
import json
from datetime import datetime

from dotenv import load_dotenv
import os

load_dotenv()

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")


WALLET = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

# ETHERSCAN API V2 URL
url = (
    "https://api.etherscan.io/v2/api"
    f"?chainid=1"
    f"&module=account"
    f"&action=txlist"
    f"&address={WALLET}"
    f"&startblock=0"
    f"&endblock=99999999"
    f"&page=1"
    f"&offset=10"
    f"&sort=desc"
    f"&apikey={API_KEY}"
)

# FETCH DATA
with urllib.request.urlopen(url) as response:
    data = json.loads(response.read().decode())

# CHECK RESPONSE
if data["status"] != "1":
    print("Error:", data.get("message"))
    print(data.get("result"))

else:
    print(f"\nLatest Transactions for {WALLET}\n")

    for tx in data["result"]:

        eth_value = int(tx["value"]) / 10**18

        time = datetime.fromtimestamp(int(tx["timeStamp"]))

        if tx["to"].lower() == WALLET.lower():
            direction = "IN"
        else:
            direction = "OUT"

        print("Direction :", direction)
        print("Hash      :", tx["hash"])
        print("From      :", tx["from"])
        print("To        :", tx["to"])
        print("ETH       :", eth_value)
        print("Time      :", time)
        print("-" * 50)
