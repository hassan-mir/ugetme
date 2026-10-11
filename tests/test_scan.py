import json
from pathlib import Path
from unittest import mock

from helpers import TempHomeTest

from ugetme import scan, vocab


class ScanTest(TempHomeTest):
    def make_tree(self) -> Path:
        root = self.home / "code"
        (root / "nimbus-api").mkdir(parents=True)
        (root / "nimbus-api" / "package.json").write_text(json.dumps({"name": "@acme/nimbus"}))
        (root / "orbit").mkdir()
        (root / "orbit" / "README.md").write_text("# Orbit Planner\n\n## Installation\n")
        (root / "orbit" / "pyproject.toml").write_text('[build-system]\nrequires = ["x"]\n\n[project]\nname = "orbit-core"\n')
        (root / ".secret").mkdir()
        (root / "node_modules").mkdir()
        (root / "notes.txt").write_text("x")
        return root

    def test_scan_reads_names_only(self):
        self.assertEqual(scan.scan([str(self.make_tree())]),
                         ["nimbus-api", "@acme/nimbus", "orbit", "Orbit Planner", "orbit-core"])

    def test_comments_inside_code_blocks_are_not_titles(self):
        root = self.home / "code"
        (root / "orbit").mkdir(parents=True)
        (root / "orbit" / "README.md").write_text("```bash\n# Install dependencies\npnpm i\n```\n# Orbit Planner\n")
        self.assertEqual(scan.scan([str(root)]), ["orbit", "Orbit Planner"])

    def test_missing_root_is_skipped(self):
        self.assertEqual(scan.scan([str(self.home / "nope")]), [])

    def test_limit(self):
        root = self.home / "many"
        for i in range(30):
            (root / f"p{i:02d}").mkdir(parents=True)
        self.assertEqual(len(scan.scan([str(root)], limit=10)), 10)

    def test_update_profile_keeps_terms(self):
        (self.home / "vocab.md").write_text('# Terms\n- Nimbus (heard: "nimbis")\n')
        self.assertEqual(scan.update_profile([str(self.make_tree())]), 5)
        v = vocab.load(self.home / "vocab.md")
        self.assertEqual((v.terms[0].term, v.projects[0]), ("Nimbus", "nimbus-api"))

    def test_default_roots(self):
        (self.home / "code").mkdir()
        with mock.patch.object(scan.Path, "home", return_value=self.home):
            self.assertEqual(scan.default_roots(), [str(self.home / "code")])
