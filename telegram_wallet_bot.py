import urllib.request
import urllib.parse
import json
import time
from datetime import datetime

from dotenv import load_dotenv
import os

load_dotenv()

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

LAST_UPDATE_ID = 0
WATCHED_WALLETS = {}   # chat_id -> wallet
LAST_TX_HASH = {}      # wallet -> last hash

CHAIN_ID = "1"  # Ethereum mainnet


def get_json(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode())


def send_message(chat_id, text):
    encoded_text = urllib.parse.quote(text)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage?chat_id={chat_id}&text={encoded_text}"
    get_json(url)


def etherscan_tx_url(tx_hash):
    return f"https://etherscan.io/tx/{tx_hash}"


def get_transactions(wallet, offset=50):
    url = (
        "https://api.etherscan.io/v2/api"
        f"?chainid={CHAIN_ID}"
        f"&module=account"
        f"&action=txlist"
        f"&address={wallet}"
        f"&startblock=0"
        f"&endblock=99999999"
        f"&page=1"
        f"&offset={offset}"
        f"&sort=desc"
        f"&apikey={ETHERSCAN_API_KEY}"
    )
    data = get_json(url)

    if data.get("status") != "1":
        return []

    return data.get("result", [])


def get_token_transactions(wallet, offset=20):
    url = (
        "https://api.etherscan.io/v2/api"
        f"?chainid={CHAIN_ID}"
        f"&module=account"
        f"&action=tokentx"
        f"&address={wallet}"
        f"&page=1"
        f"&offset={offset}"
        f"&sort=desc"
        f"&apikey={ETHERSCAN_API_KEY}"
    )
    data = get_json(url)

    if data.get("status") != "1":
        return []

    return data.get("result", [])


def detect_exchange(address):
    known = {
        "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
        "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
        "0x3f5ce5fbfe3e9af3971d1e27679b2e4a1b3c2f0": "Binance",
        "0xa090e606e30bd747d4e6245a1517ebe430f0057e": "Coinbase",
        "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
        "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": "Kraken",
    }

    return known.get(address.lower())


def analyze_wallet(wallet):
    txs = get_transactions(wallet, 50)
    token_txs = get_token_transactions(wallet, 20)

    if not txs:
        return "No transactions found or invalid wallet."

    total_in = 0
    total_out = 0
    max_tx = 0
    counterparties = set()
    exchange_hits = set()

    for tx in txs:
        value_eth = int(tx["value"]) / 10**18
        max_tx = max(max_tx, value_eth)

        from_addr = tx["from"].lower()
        to_addr = tx["to"].lower()

        if to_addr == wallet.lower():
            total_in += value_eth
            counterparties.add(from_addr)
            ex = detect_exchange(from_addr)
            if ex:
                exchange_hits.add(ex)
        else:
            total_out += value_eth
            counterparties.add(to_addr)
            ex = detect_exchange(to_addr)
            if ex:
                exchange_hits.add(ex)

    tx_count = len(txs)
    volume = total_in + total_out

    risk_score = 0
    if max_tx >= 100:
        risk_score += 35
    if volume >= 500:
        risk_score += 30
    if len(counterparties) >= 25:
        risk_score += 20
    if exchange_hits:
        risk_score += 10
    if tx_count >= 40:
        risk_score += 5

    risk_score = min(risk_score, 100)

    if max_tx >= 100 or volume >= 500:
        wallet_type = "Possible Whale 🐋"
    elif tx_count > 30:
        wallet_type = "Active Wallet ⚡"
    else:
        wallet_type = "Normal / Low Activity Wallet"

    if risk_score >= 70:
        risk_level = "HIGH 🚨"
    elif risk_score >= 40:
        risk_level = "MEDIUM ⚠️"
    else:
        risk_level = "LOW ✅"

    token_summary = "No recent ERC20 token activity."
    if token_txs:
        tokens = {}
        for t in token_txs[:10]:
            symbol = t.get("tokenSymbol", "UNKNOWN")
            tokens[symbol] = tokens.get(symbol, 0) + 1

        token_summary = "\n".join([f"{k}: {v} tx" for k, v in tokens.items()])

    exchange_text = ", ".join(exchange_hits) if exchange_hits else "No known exchange detected"

    ai_summary = (
        f"This wallet looks like {wallet_type}. "
        f"It has recent volume of {volume:.4f} ETH, largest transaction {max_tx:.4f} ETH, "
        f"and {len(counterparties)} connected wallets."
    )

    return f"""
Wallet Analysis Report

Wallet:
{wallet}

Wallet Type:
{wallet_type}

Risk Score:
{risk_score}/100 - {risk_level}

Last Checked TX Count:
{tx_count}

Total IN:
{total_in:.4f} ETH

Total OUT:
{total_out:.4f} ETH

Largest TX:
{max_tx:.4f} ETH

Unique Connected Wallets:
{len(counterparties)}

Exchange Detection:
{exchange_text}

Recent ERC20 Token Activity:
{token_summary}

AI-Style Summary:
{ai_summary}

Note:
This is heuristic analysis, not final proof.
"""


def watch_wallet(chat_id, wallet):
    WATCHED_WALLETS[chat_id] = wallet

    txs = get_transactions(wallet, 1)
    if txs:
        LAST_TX_HASH[wallet] = txs[0]["hash"]

    send_message(chat_id, f"Watching wallet:\n{wallet}\n\nI will alert you on new transactions.")


def check_alerts():
    for chat_id, wallet in list(WATCHED_WALLETS.items()):
        txs = get_transactions(wallet, 1)

        if not txs:
            continue

        latest = txs[0]
        latest_hash = latest["hash"]

        if wallet not in LAST_TX_HASH:
            LAST_TX_HASH[wallet] = latest_hash
            continue

        if latest_hash != LAST_TX_HASH[wallet]:
            LAST_TX_HASH[wallet] = latest_hash

            value_eth = int(latest["value"]) / 10**18
            direction = "IN" if latest["to"].lower() == wallet.lower() else "OUT"

            alert_type = "🚨 WHALE ALERT" if value_eth >= 100 else "🔔 NEW TX ALERT"

            msg = f"""
{alert_type}

Wallet:
{wallet}

Direction:
{direction}

Amount:
{value_eth:.4f} ETH

From:
{latest["from"]}

To:
{latest["to"]}

Hash:
{latest_hash}

Link:
{etherscan_tx_url(latest_hash)}
"""
            send_message(chat_id, msg)


def run_bot():
    global LAST_UPDATE_ID

    print("Bot started...")

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={LAST_UPDATE_ID + 1}&timeout=10"
            data = get_json(url)

            for update in data.get("result", []):
                LAST_UPDATE_ID = update["update_id"]

                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "").strip()

                if not chat_id:
                    continue

                if text == "/start":
                    send_message(
                        chat_id,
                        "Send wallet address to analyze.\n\nCommands:\n/analyze 0x...\n/watch 0x...\n/stopwatch"
                    )

                elif text.startswith("/analyze"):
                    parts = text.split()
                    if len(parts) != 2:
                        send_message(chat_id, "Use: /analyze 0xWalletAddress")
                    else:
                        wallet = parts[1]
                        send_message(chat_id, "Analyzing wallet...")
                        send_message(chat_id, analyze_wallet(wallet))

                elif text.startswith("/watch"):
                    parts = text.split()
                    if len(parts) != 2:
                        send_message(chat_id, "Use: /watch 0xWalletAddress")
                    else:
                        wallet = parts[1]
                        watch_wallet(chat_id, wallet)

                elif text == "/stopwatch":
                    if chat_id in WATCHED_WALLETS:
                        del WATCHED_WALLETS[chat_id]
                        send_message(chat_id, "Stopped watching wallet.")
                    else:
                        send_message(chat_id, "No wallet is being watched.")

                elif text.startswith("0x") and len(text) == 42:
                    send_message(chat_id, "Analyzing wallet...")
                    send_message(chat_id, analyze_wallet(text))

                else:
                    send_message(chat_id, "Send a valid Ethereum wallet or use /analyze 0x...")

            check_alerts()

        except Exception as e:
            print("Error:", e)

        time.sleep(5)


run_bot()
