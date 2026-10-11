import os
import tempfile
import unittest
from pathlib import Path

from helpers import write_jsonl

from ugetme import context
from ugetme.transcript import Turn


class ContextTest(unittest.TestCase):
    def test_build_input_sections_in_order(self):
        text = context.build_input(
            "so um fix the thing", "# Terms\n- Nimbus", [Turn("user", "hi"), Turn("assistant", "hello")],
            ["src/a.py"], "proj: src/")
        order = [text.index(tag) for tag in
                 ("<vocabulary>", "<project>", "<recent_files>", "<conversation>", "<raw_prompt>")]
        self.assertEqual(order, sorted(order))
        self.assertIn("[assistant]: hello", text)
        self.assertTrue(text.rstrip().endswith("</raw_prompt>"))

    def test_empty_parts_are_left_out(self):
        text = context.build_input("raw", "", [], [], "")
        self.assertEqual(text, "<raw_prompt>\nraw\n</raw_prompt>")

    def test_caps_turn_length_and_drops_oldest(self):
        big = [Turn("user", "old " * 5000)] + [Turn("assistant", "x" * 1900) for _ in range(30)]
        text = context.build_input("raw", "", big, [], "")
        self.assertLessEqual(len(text), context.TOTAL_CAP + 200)
        self.assertNotIn("old old", text)
        self.assertIn("[…]", context.build_input("raw", "", [Turn("user", "y" * 5000)], [], ""))

    def test_project_outline_skips_hidden_and_heavy_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("src", ".git", "node_modules"):
                Path(d, name).mkdir()
            Path(d, "README.md").write_text("x")
            outline = context.project_outline(d)
        self.assertIn("README.md", outline)
        self.assertIn("src/", outline)
        self.assertNotIn(".git", outline)
        self.assertNotIn("node_modules", outline)

    def test_gather_none_reads_nothing(self):
        settings = {"turns": 0, "last_reply": False, "file_names": False, "project_outline": False}
        self.assertEqual(context.gather(settings, "/no/file", "/tmp"), ([], [], ""))

    def test_gather_light_with_last_reply_only(self):
        path = write_jsonl([{"type": "user", "message": {"content": "q1"}},
                            {"type": "assistant", "message": {"content": [{"type": "text", "text": "a1"}]}},
                            {"type": "user", "message": {"content": "q2"}}])
        self.addCleanup(os.unlink, path)
        settings = {"turns": 0, "last_reply": True, "file_names": False, "project_outline": False}
        turns, files, outline = context.gather(settings, path, "")
        self.assertEqual([(t.role, t.text) for t in turns], [("assistant", "a1")])
