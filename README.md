# Coventry rate watch
Checks Coventry BS's first-time-buyer page once a day for the 2-year (£999 fee,
85% LTV) fixed rate and tracks changes in `rate_state.json`. No email notifications;
just persistent state that updates on each run.

## Setup

**1. Confirm the workflow is registered**
- Open the **Actions** tab on the repo.
- `Coventry rate watch` should already appear in the left sidebar — Actions is on by
  default for your own repos (only forks require manually enabling it).

**2. Test it**
- Actions tab → **Coventry rate watch** → **Run workflow** button (top right of the
  runs list) → manual trigger.
- Check the run log to see the parsed rate and any changes to the state file.

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
- Watches by fee + LTV, so it survives Coventry retiring/changing the product code.
- Check `rate_state.json` in the repo to see the current baseline and history via git log.

## Known caveats / failure modes
- **Cloud IP blocking** — some sites block datacentre IPs. If fetches from Actions start
  failing or returning empty results, fall back to running the script locally via Windows
  Task Scheduler (Basic Task → daily → "Start a program" → `python` with the script path).
- **Page structure changes** — if Coventry restructures the page, the regex/selectors in
  `coventry_rate_watch.py` may need adjusting. Run `python coventry_rate_watch.py --debug`
  to print everything parsed, which makes diagnosing the change quick.
