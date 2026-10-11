import os

from helpers import TempHomeTest

from ugetme import clean, config, state

RAW = "so um ask nimbis to review the login change"


class CleanTest(TempHomeTest):
    def setUp(self):
        super().setUp()
        self.fake_output("Ask Nimbus to review the login change.", [("nimbis", "Nimbus")])
        self.cfg = config.load()

    def test_success_is_logged(self):
        r = clean.clean_text(RAW, self.cfg)
        self.assertEqual((r.clean, r.changes, r.failed), ("Ask Nimbus to review the login change.", [("nimbis", "Nimbus")], ""))
        self.assertEqual(len(r.id), 12)
        entry = state.read_log(1)[0]
        self.assertEqual((entry["event"], entry["id"], entry["raw"]), ("cleaned", r.id, RAW))

    def test_failure_returns_the_raw_text(self):
        os.environ["FAKE_CLAUDE_MODE"] = "fail"
        r = clean.clean_text(RAW, self.cfg)
        self.assertEqual((r.clean, r.view), (RAW, RAW))
        self.assertIn("not logged in", r.failed)
        self.assertEqual(state.read_log(1)[0]["event"], "failed")

    def test_logs_never_reach_the_engine_and_come_back_exact(self):
        trace = "Traceback (most recent call last):\n  File \"a.py\", line 1\nValueError: x"
        self.fake_output("Why does this fail? ⟦ugetme:1⟧")
        log = self.fake_log()
        r = clean.clean_text("why does this fail\n" + trace, self.cfg)
        self.assertNotIn("Traceback", self.fake_calls(log)[0]["stdin"])
        self.assertEqual(r.clean, "Why does this fail? " + trace)

    def test_user_and_project_vocabulary_reach_the_engine(self):
        (self.home / "vocab.md").write_text('# Terms\n- Nimbus (heard: "nimbis")\n')
        proj = self.home / "proj"
        (proj / ".claude").mkdir(parents=True)
        (proj / ".claude" / "ugetme.md").write_text('# Terms\n- Orbit (heard: "orbits")\n')
        log = self.fake_log()
        clean.clean_text(RAW, self.cfg, {"cwd": str(proj), "transcript_path": ""})
        stdin = self.fake_calls(log)[0]["stdin"]
        self.assertIn('Nimbus (heard: "nimbis")', stdin)
        self.assertIn('Orbit (heard: "orbits")', stdin)
        self.assertIn("<project>", stdin)

    def test_correction_protects_a_recent_change(self):
        (self.home / "vocab.md").write_text('# Terms\n- Nimbus (heard: "nimbis")\n')
        log = self.fake_log()
        clean.clean_text("no, nimbis was right, it is a different app", self.cfg, None, [("nimbis", "Nimbus")])
        stdin = self.fake_calls(log)[0]["stdin"]
        self.assertIn("# Keep\n- nimbis", stdin)
        self.assertNotIn('heard: "nimbis"', stdin)

    def test_repeated_name_without_correction_is_not_protected(self):
        (self.home / "vocab.md").write_text('# Terms\n- Nimbus (heard: "nimbis")\n')
        log = self.fake_log()
        clean.clean_text("please ask nimbis about the plan for tomorrow", self.cfg, None, [("nimbis", "Nimbus")])
        self.assertIn('Nimbus (heard: "nimbis")', self.fake_calls(log)[0]["stdin"])
