import os
import stat
import tempfile
import unittest
from pathlib import Path

from ugetme import vocab

SAMPLE = """# Terms
- Nimbus (heard: "nimbis", "nimbos")
- Handy (heard: "Andy")

# Style
- Prefers lists for multiple steps.

# Keep
- nimby

# Projects (auto)
- nimbus-api
- Orbit Planner
"""


class VocabTest(unittest.TestCase):
    def test_parse_and_render_round_trip(self):
        v = vocab.parse(SAMPLE)
        self.assertEqual([e.term for e in v.terms], ["Nimbus", "Handy"])
        self.assertEqual(v.terms[0].heard, ["nimbis", "nimbos"])
        self.assertEqual(v.style, ["Prefers lists for multiple steps."])
        self.assertEqual(v.keep, ["nimby"])
        self.assertEqual(v.projects, ["nimbus-api", "Orbit Planner"])
        self.assertEqual(vocab.render(v), SAMPLE)

    def test_hand_written_lines_are_accepted(self):
        v = vocab.parse("# Terms\n- Orbit\n- ugetme (heard: you get me)\nrandom text\n# Other\n- ignored\n")
        self.assertEqual([(e.term, e.heard) for e in v.terms], [("Orbit", []), ("ugetme", ["you get me"])])

    def test_add_confirmed_new_and_existing(self):
        v = vocab.parse(SAMPLE)
        vocab.add_confirmed(v, "cloud code", "Claude Code")
        vocab.add_confirmed(v, "Andie", "handy")
        vocab.add_confirmed(v, "andy", "Handy")
        self.assertEqual(v.terms[-1].term, "Claude Code")
        self.assertEqual(v.terms[1].heard, ["Andy", "Andie"])

    def test_keep_removes_alias_and_fix_removes_keep(self):
        v = vocab.parse(SAMPLE)
        vocab.keep(v, "Nimbis")
        self.assertEqual(v.terms[0].heard, ["nimbos"])
        self.assertEqual(v.keep, ["nimby", "Nimbis"])
        vocab.keep(v, "NIMBIS")
        self.assertEqual(v.keep, ["nimby", "Nimbis"])
        vocab.add_confirmed(v, "nimby", "Nimbus")
        self.assertEqual(v.keep, ["Nimbis"])

    def test_forget_term_or_keep_word(self):
        v = vocab.parse(SAMPLE)
        self.assertTrue(vocab.forget(v, "nimbus"))
        self.assertFalse(vocab.forget(v, "nimbus"))
        self.assertTrue(vocab.forget(v, "NIMBY"))
        self.assertEqual(([e.term for e in v.terms], v.keep), (["Handy"], []))

    def test_merged_project_wins_and_lists_join(self):
        user = vocab.parse(SAMPLE)
        project = vocab.parse('# Terms\n- Nimbus (heard: "nimbus cloud")\n\n# Style\n- Use British spelling.\n\n'
                              '# Keep\n- orbits\n\n# Projects (auto)\n- orbit-core\n')
        m = vocab.merged(user, project)
        nimbus = [e for e in m.terms if e.term == "Nimbus"]
        self.assertEqual(nimbus[0].heard, ["nimbus cloud"])
        self.assertIn("Use British spelling.", m.style)
        self.assertEqual(m.keep, ["nimby", "orbits"])
        self.assertEqual(m.projects, ["nimbus-api", "Orbit Planner", "orbit-core"])

    def test_tidy_merges_duplicates(self):
        v = vocab.parse(SAMPLE)
        v.style.append("Prefers lists for multiple steps.")
        v.keep.append("NIMBY")
        v.terms.append(vocab.Entry("nimbus", ["nimbus cloud", "nimbis"]))
        vocab.tidy(v)
        self.assertEqual([e.term for e in v.terms], ["Nimbus", "Handy"])
        self.assertEqual(v.terms[0].heard, ["nimbis", "nimbos", "nimbus cloud"])
        self.assertEqual((len(v.style), v.keep), (1, ["nimby"]))

    def test_load_missing_and_save_private(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "vocab.md"
            self.assertEqual(vocab.load(p).terms, [])
            vocab.save(p, vocab.parse(SAMPLE))
            self.assertEqual(vocab.load(p).terms[0].term, "Nimbus")
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
