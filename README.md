# Coventry rate watch
Checks Coventry BS's first-time-buyer page once a day and emails a status
update every run for the 2-year (£999 fee, 85% LTV) fixed rate. The subject
line flags it clearly when the rate has DROPPED. Emailing every run (rather
than only on a drop) is deliberate: a missing email is itself a signal that
the job failed, instead of silently trusting "no news = no change."

## Setup

**1. Create a Gmail App Password**
- Go to your Google Account → **Security**.
- Turn on **2-Step Verification** if it isn't already on.
- Go to **Security → App passwords**.
- Create a new one for "Mail" (any device name works).
- Copy the 16-character password — you won't be able to see it again.

**2. Add the repository secrets**
- In this repo on GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
- Add three secrets:
  - `SMTP_USER` — the sending Gmail address.
  - `SMTP_PASS` — the 16-character App Password from step 1.
  - `TO_EMAIL` — where alerts should land (can be the same Gmail address).

**3. Confirm the workflow is registered**
- Open the **Actions** tab on the repo.
- `Coventry rate watch` should already appear in the left sidebar — Actions is on by
  default for your own repos (only forks require manually enabling it).

**4. Test it**
- Actions tab → **Coventry rate watch** → **Run workflow** button (top right of the
  runs list) → manual trigger.
- Check the run log for errors — every successful run sends an email, so this alone
  confirms delivery works.
- To specifically confirm the "DROPPED" subject line works, temporarily lower the
  baseline in `rate_state.json` (e.g. `4.44` → `4.50`) and re-run, then revert it
  once the test email arrives.

## Baseline
- `rate_state.json` is seeded at `4.44` under the key `"2yr|999|85"`.
- The key is stable (fee + LTV based), so it survives the product's end date rolling forward.
- The workflow commits an updated `rate_state.json` back to the repo after each run if the rate changed.

## Schedule
- Runs once daily: 08:00 UTC (~09:00 BST).
- Can also be triggered manually any time via **Actions → Run workflow**.
- GitHub cron is "best effort" and can be delayed under load, and GitHub auto-disables
  scheduled workflows after 60 days of repo inactivity (any push/commit resets that clock).

## Notes
- Personal use, one email per day regardless of outcome — the subject line says
  "DROPPED" only when the rate has actually fallen, so it's easy to filter/skim for.
- Watches by fee + LTV, so it survives Coventry retiring/changing the product code.
- It's a backstop that tells me *when* to act — the broker actually requests any reissue.

## Known caveats / failure modes
- **Cloud IP blocking** — some sites block datacentre IPs. If fetches from Actions start
  failing or returning empty results, fall back to running the script locally via Windows
  Task Scheduler (Basic Task → daily → "Start a program" → `python` with the script path,
  env vars set in the task or a `.env` file).
- **Page structure changes** — if Coventry restructures the page, the regex/selectors in
  `coventry_rate_watch.py` may need adjusting. Run `python coventry_rate_watch.py --debug`
  to print everything parsed, which makes diagnosing the change quick.
- **Rates move slowly** — expect infrequent alerts; the tool's main value is not having to
  remember to check manually. Forward any drop alert to the broker to action a reissue.
