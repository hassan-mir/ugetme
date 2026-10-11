import json
import os
import stat
from unittest import mock

from helpers import TempHomeTest

from ugetme import state


class StateTest(TempHomeTest):
    def test_pending_is_per_session_and_popped_once(self):
        state.save_pending("a", "text A", [("nimbis", "Nimbus")], "id1")
        state.save_pending("b", "text B")
        self.assertEqual(state.pop_pending("a"), {"text": "text A", "changes": [("nimbis", "Nimbus")], "output_id": "id1"})
        self.assertIsNone(state.pop_pending("a"))
        self.assertEqual(state.pop_pending("b")["text"], "text B")

    def test_pending_expires(self):
        state.save_pending("a", "old")
        real = state.time.time
        with mock.patch.object(state.time, "time", return_value=real() + state.PENDING_MAX_AGE + 1):
            self.assertIsNone(state.pop_pending("a"))

    def test_session_files_are_private_safe_and_pruned(self):
        state.save_pending("../../evil", "x")
        files = list((self.home / "sessions").glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].parent, self.home / "sessions")
        self.assertEqual(stat.S_IMODE(os.stat(files[0]).st_mode), 0o600)
        for i in range(state.MAX_SESSIONS + 5):
            state.save_pending(f"s{i}", "x")
        self.assertLessEqual(len(list((self.home / "sessions").glob("*.json"))), state.MAX_SESSIONS)

    def test_log_rotates_caps_and_is_private(self):
        for i in range(state.LOG_MAX + 1):
            state.log({"n": i})
        lines = (self.home / "log.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), state.LOG_KEEP)
        self.assertEqual(json.loads(lines[-1])["n"], state.LOG_MAX)
        self.assertEqual(stat.S_IMODE(os.stat(self.home / "log.jsonl").st_mode), 0o600)
        state.log({"raw": "x" * (state.LOG_FIELD_CAP + 100)})
        self.assertLess(len(state.read_log(1)[0]["raw"]), state.LOG_FIELD_CAP + 10)

    def test_log_disabled_and_read_log(self):
        state.log({"n": 1}, enabled=False)
        self.assertEqual(state.read_log(), [])
        state.log({"n": 1})
        (self.home / "log.jsonl").write_text((self.home / "log.jsonl").read_text() + "{broken\n")
        state.log({"n": 2})
        self.assertEqual([e["n"] for e in state.read_log()], [1, 2])
