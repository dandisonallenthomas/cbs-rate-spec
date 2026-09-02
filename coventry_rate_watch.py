#!/usr/bin/env python3
"""Coventry BS first-time-buyer rate watcher. Checks rates and persists state.

Usage:
  python coventry_rate_watch.py            # check + update state (used by CI)
  python coventry_rate_watch.py --debug    # print all parsed products, no state update
"""
import os
import re
import sys
import json
import datetime as dt

import requests
from bs4 import BeautifulSoup

URL = "https://www.coventrybuildingsociety.co.uk/member/mortgages/first-time-buyer.html"
TARGET_FEE = 999
TARGET_LTV = 85
STATE_KEY = f"2yr|{TARGET_FEE}|{TARGET_LTV}"   # stable key; independent of end date
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rate_state.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"}
HEADER_RE = re.compile(r"(\d\.\d{2})%\s*Fixed\s*(?:Rate\s*)?(?:to|until)\s*(\d{2}\.\d{2}\.\d{2})", re.I)


def fetch_products():
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    text = BeautifulSoup(resp.text, "html.parser").get_text("\n")
    matches = list(HEADER_RE.finditer(text))
    products = []
    for i, m in enumerate(matches):
        block = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        fee_m = re.search(r"Product fee\D*£?\s*([\d,]+)", block, re.I)
        ltv_m = re.search(r"Max loan to value:\s*(\d+)\s*%", block, re.I)
        products.append({
            "rate": float(m.group(1)),
            "end_date": m.group(2),
            "fee": int(fee_m.group(1).replace(",", "")) if fee_m else None,
            "ltv": int(ltv_m.group(1)) if ltv_m else None,
        })
    return products


def target_group(products):
    grp = [p for p in products if p["fee"] == TARGET_FEE and p["ltv"] == TARGET_LTV]
    grp.sort(key=lambda p: dt.datetime.strptime(p["end_date"], "%d.%m.%y"))
    return grp


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def describe(grp):
    return "\n".join(
        f"  {p['rate']:.2f}%  fixed to {p['end_date']}  (£{p['fee']} fee, {p['ltv']}% LTV)"
        for p in grp
    ) or "  (no matching products)"


def run():
    debug = "--debug" in sys.argv

    products = fetch_products()
    if debug:
        for p in products:
            print(p)
        print("\nTarget group:\n" + describe(target_group(products)))
        return

    grp = target_group(products)
    if not grp:
        print("Target product NOT FOUND — Coventry may have changed product codes.")
        return

    two_year = grp[0]
    now = two_year["rate"]
    state = load_state()
    prev = state.get(STATE_KEY)

    if prev is None:
        print(f"Baseline set at {now:.2f}%.")
    elif now < prev:
        print(f"Rate DROPPED to {now:.2f}% (was {prev:.2f}%)")
    elif now > prev:
        print(f"Rate rose {prev:.2f}% -> {now:.2f}%")
    else:
        print(f"No change ({now:.2f}%).")

    state[STATE_KEY] = now
    save_state(state)


def main():
    run()


if __name__ == "__main__":
    main()
