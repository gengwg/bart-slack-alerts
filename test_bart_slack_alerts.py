"""Run: python3 -m unittest test_bart_slack_alerts.py"""
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

spec = importlib.util.spec_from_file_location("bart", os.path.join(os.path.dirname(__file__), "bart-slack-alerts.py"))
bart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bart)


def entry(id_, text):
    return {"@id": id_, "type": "DELAY", "posted": "Fri Oct 10 2026 08:00 AM PDT",
            "description": {"#cdata-section": text}}


# The live shape on a quiet day: no @id.
QUIET = {"station": "", "description": {"#cdata-section": "No advisories issued."}}


class Run:
    """Calls main() with a fake BART API and records what reaches Slack."""

    def __init__(self, test, bsa, args=(), fail_on=None):
        self.posts = []

        def get(url, data=None, headers=None):
            if url == bart.API:
                return json.dumps({"root": {"bsa": bsa}}).encode()
            if fail_on and len(self.posts) == fail_on:
                raise OSError("slack down")
            self.posts.append(json.loads(data)["text"])

        with mock.patch.object(bart, "get", get), mock.patch("sys.argv", ["bart", *args]), \
                mock.patch.dict(os.environ, {"BART_SLACK_WEBHOOK": "https://hooks.example/x"}):
            bart.main()


class BartTest(unittest.TestCase):
    def setUp(self):
        self.state = os.path.join(tempfile.mkdtemp(), "state.json")
        patcher = mock.patch.object(bart, "STATE", self.state)
        patcher.start()
        self.addCleanup(patcher.stop)

    def seen(self):
        return json.load(open(self.state))

    def test_quiet_day_placeholder_posts_nothing(self):
        self.assertEqual(Run(self, [QUIET]).posts, [])

    def test_single_advisory_as_bare_object(self):
        self.assertEqual(len(Run(self, entry("1", "Delays at Embarcadero.")).posts), 1)

    def test_same_advisory_posts_once(self):
        Run(self, [entry("1", "Delays at Embarcadero.")])
        self.assertEqual(Run(self, [entry("1", "Delays at Embarcadero.")]).posts, [])

    def test_reworded_advisory_posts_again(self):
        Run(self, [entry("1", "Delays at Embarcadero.")])
        self.assertEqual(len(Run(self, [entry("1", "Delays at Embarcadero, now 15 minutes.")]).posts), 1)

    def test_seed_records_without_posting(self):
        self.assertEqual(Run(self, [entry("1", "a"), entry("2", "b")], ["--seed"]).posts, [])
        self.assertEqual(len(self.seen()), 2)

    def test_dry_run_touches_neither_slack_nor_state(self):
        self.assertEqual(Run(self, [entry("1", "a")], ["--dry-run"]).posts, [])
        self.assertFalse(os.path.exists(self.state))

    def test_advisory_seen_over_30_days_ago_posts_again(self):
        Run(self, [entry("1", "a")])
        key, = self.seen()
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        json.dump({key: old}, open(self.state, "w"))
        self.assertEqual(len(Run(self, [entry("1", "a")]).posts), 1)

    def test_slack_failure_keeps_what_landed(self):
        with self.assertRaises(OSError):
            Run(self, [entry("1", "a"), entry("2", "b")], fail_on=1)
        self.assertEqual(len(self.seen()), 1)


if __name__ == "__main__":
    unittest.main()
