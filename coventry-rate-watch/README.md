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
