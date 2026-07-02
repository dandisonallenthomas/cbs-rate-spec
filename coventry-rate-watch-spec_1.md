# Build spec: Coventry Building Society rate watcher (GitHub Actions + email)

## Objective
A small Python tool, run on a schedule by GitHub Actions, that checks Coventry
Building Society's first-time-buyer mortgage page for a target product and emails
me if the rate **drops**. No server or local machine required — it runs entirely
in GitHub's cloud.

**Target product:** 2-year fixed, £999 fee, 85% LTV. Currently 4.44% (fixed to
31.12.28). I want an email if it falls below the last rate seen (baseline seeded
at 4.44%).

**Notification:** email, sent from a Gmail account to itself via SMTP + App Password.

## Key design decisions (please preserve these)
1. **Parse from static HTML.** The rates/fees/LTVs are present in the page HTML
   (only the monthly-payment figure is JS-rendered, which we don't need), so
   `requests` + `BeautifulSoup` is sufficient — no headless browser.
2. **Match by fee + LTV, not product code.** Lenders often retire a product code
   when they change a rate. Matching on £999 + 85% LTV and taking the soonest-fix
   product survives code changes. If no match is found, email a "check manually"
   notice rather than fail silently.
3. **Stable logical state key.** Store the baseline under `"2yr|999|85"` — NOT the
   literal end date — so when the 2-year product's end date rolls forward the
   baseline isn't lost.
4. **Persist state by committing it back to the repo.** Actions runners are
   ephemeral. After each run, commit `rate_state.json` if it changed. Requires
   `permissions: contents: write`.
5. **Seed the baseline** in `rate_state.json` at 4.44%, so a drop can be caught on
   the first scheduled run.
6. **Secrets, never hard-coded.** SMTP creds come from GitHub repo secrets.
7. **Be polite.** Twice-daily schedule, real browser User-Agent, personal use only.
8. **Fail loud, not silent.** On fetch/parse/email errors, email a heads-up so I
   know the watcher needs attention (and the Actions run should show as failed).

## Repository structure
```
coventry-rate-watch/
├── coventry_rate_watch.py
├── requirements.txt
├── rate_state.json                # seeded baseline, committed & updated by CI
├── .gitignore
├── README.md
└── .github/
    └── workflows/
        └── rate-watch.yml
```

---

## File: `requirements.txt`
```
requests
beautifulsoup4
```

## File: `.gitignore`
```
__pycache__/
*.pyc
.env
```
> Note: do **not** gitignore `rate_state.json` — it must be committed so state persists.

## File: `rate_state.json` (seed)
```json
{
  "2yr|999|85": 4.44
}
```

## File: `coventry_rate_watch.py`
```python
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
```

## File: `.github/workflows/rate-watch.yml`
```yaml
name: Coventry rate watch

on:
  schedule:
    - cron: '0 8,17 * * *'   # 08:00 & 17:00 UTC daily (~09:00 & 18:00 BST)
  workflow_dispatch:          # manual "Run workflow" button in the Actions tab

permissions:
  contents: write             # required to commit the updated state file

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install -r requirements.txt

      - name: Run rate watcher
        env:
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          TO_EMAIL:  ${{ secrets.TO_EMAIL }}
        run: python coventry_rate_watch.py

      - name: Persist state if changed
        run: |
          if [ -n "$(git status --porcelain rate_state.json)" ]; then
            git config user.name "rate-watch-bot"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add rate_state.json
            git commit -m "Update rate state [skip ci]"
            git push
          else
            echo "No state change."
          fi
```

## File: `README.md` (suggested contents)
```markdown
# Coventry rate watch
Checks Coventry BS's first-time-buyer page twice daily and emails me if the
2-year (£999 fee, 85% LTV) fixed rate drops below the last seen rate.

## Setup
1. Create a Gmail App Password (Google Account > Security > 2-Step Verification > App passwords).
2. In this repo: Settings > Secrets and variables > Actions > New repository secret. Add:
   - `SMTP_USER` = the sending Gmail address
   - `SMTP_PASS` = the 16-char App Password
   - `TO_EMAIL`  = where alerts go (can be the same address)
3. Enable Actions (Actions tab). Runs automatically on schedule; or hit "Run workflow" to test.

## Baseline
`rate_state.json` is seeded at 4.44%. The workflow updates and commits it after each run.

## Notes
- Personal use, twice daily. Watches by fee + LTV, so survives product-code changes.
- It's a backstop that tells me *when* to act — the broker actually requests any reissue.
```

---

## Setup steps for me (after Claude Code pushes the repo)
1. **Gmail App Password:** Google Account → Security → turn on 2-Step Verification →
   App passwords → create one for "Mail" → copy the 16-character password.
2. **Add repo secrets:** repo → Settings → Secrets and variables → Actions →
   New repository secret, three times: `SMTP_USER`, `SMTP_PASS`, `TO_EMAIL`.
3. **Enable Actions** if prompted (Actions tab).
4. **Test now:** Actions tab → "Coventry rate watch" → "Run workflow". Check the log,
   and confirm a run of `--report` (or temporarily lower the baseline in
   `rate_state.json` to, say, 4.50 and re-run) triggers a test email.

## Known caveats / failure modes
- **Cloud IP blocking:** some sites block datacentre IPs via their firewall. If the
  fetch starts returning errors/empty from Actions, the fallback is to run the same
  script locally on Windows via **Task Scheduler** (create a Basic Task → daily →
  "Start a program" → `python` with the script path, and set the env vars in the
  task or a `.env`). Ask me and I'll write that version.
- **Page structure change:** if Coventry restructures the page, the parser may need
  the regex/selectors adjusted. The `--debug` flag prints what it parsed, which makes
  fixing it quick.
- **Rates move slowly.** Expect small moves; this mainly saves me from remembering to
  check. Any alert should be forwarded to the broker (Josephine), who actions the reissue.
```
