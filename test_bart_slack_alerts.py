"""Run: python3 -m unittest test_bart_slack_alerts.py"""
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

HERE = os.path.dirname(__file__)
SCRIPT = os.path.join(HERE, "bart-slack-alerts.py")
spec = importlib.util.spec_from_file_location("bart", SCRIPT)
bart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bart)


def entry(id_, text):
    return {"@id": id_, "type": "DELAY", "posted": "Fri Oct 10 2026 08:00 AM PDT",
            "description": {"#cdata-section": text}}


# The live shape on a quiet day: no @id.
QUIET = {"station": "", "description": {"#cdata-section": "No advisories issued."}}


class Run:
    """Calls main() with a fake BART API and records what reaches Slack."""

    def __init__(self, bsa, args=(), fail_on=None):
        self.posts = []

        def get(url, data=None, headers=None):
            if url == bart.API:
                return json.dumps({"root": {"bsa": bsa}}).encode()
            if fail_on and len(self.posts) == fail_on:
                raise OSError("slack down")
            self.posts.append(json.loads(data)["text"])

        env = {"BART_SLACK_WEBHOOK": "https://hooks.example/x"}
        with mock.patch.object(bart, "get", get), \
                mock.patch("sys.argv", ["bart", *args]), \
                mock.patch.dict(os.environ, env):
            bart.main()


class BartTest(unittest.TestCase):
    def setUp(self):
        self.state = os.path.join(tempfile.mkdtemp(), "state.json")
        patcher = mock.patch.object(bart, "STATE", self.state)
        patcher.start()
        self.addCleanup(patcher.stop)

    def seen(self):
        with open(self.state) as f:
            return json.load(f)

    def test_quiet_day_placeholder_posts_nothing(self):
        self.assertEqual(Run([QUIET]).posts, [])

    def test_single_advisory_as_bare_object(self):
        self.assertEqual(len(Run(entry("1", "Delays at Embarcadero.")).posts), 1)

    def test_same_advisory_posts_once(self):
        Run([entry("1", "Delays at Embarcadero.")])
        self.assertEqual(Run([entry("1", "Delays at Embarcadero.")]).posts, [])

    def test_reworded_advisory_posts_again(self):
        Run([entry("1", "Delays at Embarcadero.")])
        again = Run([entry("1", "Delays at Embarcadero, now 15 minutes.")])
        self.assertEqual(len(again.posts), 1)

    def test_seed_records_without_posting(self):
        seeded = Run([entry("1", "a"), entry("2", "b")], ["--seed"])
        self.assertEqual(seeded.posts, [])
        self.assertEqual(len(self.seen()), 2)

    def test_dry_run_touches_neither_slack_nor_state(self):
        self.assertEqual(Run([entry("1", "a")], ["--dry-run"]).posts, [])
        self.assertFalse(os.path.exists(self.state))

    def test_advisory_seen_over_30_days_ago_posts_again(self):
        Run([entry("1", "a")])
        key, = self.seen()
        old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
        with open(self.state, "w") as f:
            json.dump({key: old}, f)
        self.assertEqual(len(Run([entry("1", "a")]).posts), 1)

    def test_corrupt_state_file_is_replaced(self):
        with open(self.state, "w") as f:
            f.write("{truncated")
        self.assertEqual(len(Run([entry("1", "a")]).posts), 1)
        self.assertEqual(len(self.seen()), 1)

    def test_crash_mid_write_keeps_old_state(self):
        Run([entry("1", "a")])
        before = self.seen()
        with mock.patch.object(bart.json, "dump", side_effect=OSError("disk full")), \
                self.assertRaises(OSError):
            Run([entry("2", "b")])
        self.assertEqual(self.seen(), before)

    def test_slack_failure_keeps_what_landed(self):
        with self.assertRaises(OSError):
            Run([entry("1", "a"), entry("2", "b")], fail_on=1)
        self.assertEqual(len(self.seen()), 1)


if __name__ == "__main__":
    unittest.main()
