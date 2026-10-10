#!/usr/bin/env python3
"""Post new BART service advisories to a Slack channel.

Polls BART's advisory API and posts advisories it has not seen before. Each
advisory is keyed by its BART id plus a hash of its text, so a recurring notice
posts once but a reworded one posts again.

Config:
  BART_SLACK_WEBHOOK  Slack incoming webhook URL (required unless --dry-run)
  BART_STATE_FILE     seen-key store (default ~/.local/state/bart-slack-alerts.json)

Flags:
  --dry-run  print what would be posted, touching neither Slack nor the state
  --seed     mark today's advisories as seen without posting, so a cold start
             does not dump the current backlog into the channel
"""

import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# BART publishes this key openly for public use of the legacy API.
API = "https://api.bart.gov/api/bsa.aspx?cmd=bsa&key=MW9S-E7SL-26DU-VV8V&json=y"
STATE = os.environ.get(
    "BART_STATE_FILE", os.path.expanduser("~/.local/state/bart-slack-alerts.json")
)
# BART keeps advisory ids stable for a long time; a month of memory is plenty to
# stop reposts without letting the state file grow forever.
FORGET_AFTER = timedelta(days=30)


def get(url, data=None, headers=None):
    # BART 403s urllib's default User-Agent.
    hdrs = {"User-Agent": "bart-slack-alerts/1.0"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def advisories():
    bsa = json.loads(get(API))["root"]["bsa"]
    if isinstance(bsa, dict):  # the API drops the list when there is one entry
        bsa = [bsa]
    out = []
    for e in bsa:
        if "@id" not in e:  # quiet-day placeholder, e.g. "No advisories issued."
            continue
        text = e["description"]["#cdata-section"].strip()
        if "no delays reported" in text.lower():
            continue
        key = f"{e['@id']}:{hashlib.sha1(text.encode()).hexdigest()[:8]}"
        out.append((key, e.get("type", "ADVISORY"), text, e.get("posted", "")))
    return out


def post(webhook, kind, text, posted):
    body = f"*BART {kind}*\n{text}"
    if posted:
        body += f"\n_posted {posted}_"
    get(
        webhook,
        data=json.dumps({"text": body}).encode(),
        headers={"Content-Type": "application/json"},
    )


def main():
    dry = "--dry-run" in sys.argv
    seed = "--seed" in sys.argv
    webhook = os.environ.get("BART_SLACK_WEBHOOK", "")
    if not webhook and not (dry or seed):
        sys.exit("BART_SLACK_WEBHOOK is not set.")

    now = datetime.now(timezone.utc)
    try:
        seen = json.load(open(STATE))
    except FileNotFoundError:
        seen = {}
    seen = {
        k: v
        for k, v in seen.items()
        if now - datetime.fromisoformat(v) < FORGET_AFTER
    }

    new = [a for a in advisories() if a[0] not in seen]
    if not new:
        return

    try:
        for key, kind, text, posted in new:
            if dry:
                print(f"[{kind}] {text}\n")
                continue
            if not seed:
                post(webhook, kind, text, posted)
            seen[key] = now.isoformat()
    finally:
        # Record whatever landed, so a mid-run Slack failure cannot re-post.
        if not dry:
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            json.dump(seen, open(STATE, "w"))


if __name__ == "__main__":
    main()
