# bart-slack-alerts

Posts new [BART](https://www.bart.gov/) service advisories to a Slack channel.
One stdlib-only Python script, run every 5 minutes by a systemd user timer.

## Webhook URL

1. At https://api.slack.com/apps, create an app from scratch in your workspace.
2. Under **Incoming Webhooks**, turn them on and click **Add New Webhook**.
3. Pick the channel and allow. A company workspace may need admin approval.
4. Copy the URL. Anyone holding it can post to that channel, so keep it in the env file only.

## Install

```bash
install -Dm755 bart-slack-alerts.py ~/.local/bin/bart-slack-alerts.py
install -Dm600 env.example ~/.config/bart-alerts/env   # then set your Slack incoming webhook URL
cp systemd/bart-slack-alerts.{service,timer} ~/.config/systemd/user/

set -a; . ~/.config/bart-alerts/env; set +a
~/.local/bin/bart-slack-alerts.py --seed      # mark current advisories as seen, so the first run posts nothing old
systemctl --user daemon-reload
systemctl --user enable --now bart-slack-alerts.timer
```

Test the webhook without putting the URL on the command line:

```bash
curl -s -X POST -H 'Content-Type: application/json' --data '{"text":"test"}' "$BART_SLACK_WEBHOOK"; echo   # prints ok
```

`--dry-run` prints what would be posted without touching Slack or the state file.

## Behaviour

- Each advisory is keyed by its BART id plus a hash of its text, so a repeat posts once and a reworded update posts again.
- Seen keys are forgotten after 30 days. State lives in `~/.local/state/bart-slack-alerts.json` (`BART_STATE_FILE` overrides).
- If Slack fails mid-run, the advisories already posted are still recorded, so nothing posts twice.

## BART API quirks

- It returns 403 for urllib's default User-Agent, so the script sends its own.
- With one advisory, `bsa` is a bare object instead of a list.
- On a quiet day it returns a placeholder entry ("No advisories issued.") with no `@id`.

## Troubleshooting

- Service fails with `Result: resources` and 0B memory: `~/.config/bart-alerts/env` is missing.
- `systemctl --user list-timers bart-slack-alerts.timer` lists nothing: the timer is not enabled.

## Test

```bash
python3 -m unittest test_bart_slack_alerts.py
```
