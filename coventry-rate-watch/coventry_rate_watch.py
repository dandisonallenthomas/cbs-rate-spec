#!/usr/bin/env python3
"""Coventry BS first-time-buyer rate watcher. Emails on a rate DROP.

Usage:
  python coventry_rate_watch.py            # check + alert on drop (used by CI)
  python coventry_rate_watch.py --debug    # print all parsed products, no email
  python coventry_rate_watch.py --report   # email the current target rate now
"""
import os
import re
import sys
import json
import smtplib
import datetime as dt
from email.message import EmailMessage

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


def send_email(subject, body):
    user, pw, to = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS"), os.environ.get("TO_EMAIL")
    if not all([user, pw, to]):
        print("!! Email creds missing; would have sent:\n", subject, "\n", body)
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"Email sent: {subject}")


def describe(grp):
    return "\n".join(
        f"  {p['rate']:.2f}%  fixed to {p['end_date']}  (£{p['fee']} fee, {p['ltv']}% LTV)"
        for p in grp
    ) or "  (no matching products)"


def run():
    debug = "--debug" in sys.argv
    report = "--report" in sys.argv

    products = fetch_products()
    if debug:
        for p in products:
            print(p)
        print("\nTarget group:\n" + describe(target_group(products)))
        return

    grp = target_group(products)
    if not grp:
        send_email("Coventry rate watch: target product NOT FOUND",
                   "No £999 / 85% LTV fixed product on the page today — Coventry may have "
                   f"changed product codes. Check manually:\n{URL}")
        return

    two_year = grp[0]
    now = two_year["rate"]
    state = load_state()
    prev = state.get(STATE_KEY)

    if report:
        send_email(f"Coventry rate today: {now:.2f}%",
                   "Current £999 / 85% LTV products:\n" + describe(grp) + f"\n\n{URL}")

    if prev is None:
        print(f"Baseline set at {now:.2f}%.")
    elif now < prev:
        send_email(f"Coventry rate DROPPED to {now:.2f}% (was {prev:.2f}%)",
                   f"The 2-year fix (£999 fee, 85% LTV) dropped from {prev:.2f}% to {now:.2f}%.\n\n"
                   f"All matching products today:\n{describe(grp)}\n\n"
                   f"If within ~2-3 weeks of completion, ask Josephine about reissuing at the lower rate.\n\n{URL}")
    elif now > prev:
        print(f"Rate rose {prev:.2f}% -> {now:.2f}% (no alert).")
    else:
        print(f"No change ({now:.2f}%).")

    state[STATE_KEY] = now
    save_state(state)


def main():
    try:
        run()
    except Exception as e:
        # Fail loud: notify, then re-raise so the Actions run is marked failed.
        send_email("Coventry rate watch ERROR", f"The watcher hit an error:\n\n{e!r}\n\nCheck the run: {URL}")
        raise


if __name__ == "__main__":
    main()
