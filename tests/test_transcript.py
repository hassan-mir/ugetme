import os
import unittest

from helpers import write_jsonl

from ugetme import transcript


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


RECORDS = [
    {"type": "system", "content": "ignored"},
    user("first question <system-reminder>secret</system-reminder>"),
    assistant({"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Let me look."}),
    assistant({"type": "tool_use", "name": "Read", "input": {"file_path": "src/auth/login.ts"}}),
    {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "file body"}]}},
    assistant({"type": "text", "text": "The login checks the password."}),
    user("<command-name>/clear</command-name>"),
    {"type": "user", "isSidechain": True, "message": {"role": "user", "content": "subagent text"}},
    user([{"type": "text", "text": "second question"}]),
    assistant({"type": "tool_use", "name": "Edit", "input": {"file_path": "src/auth/login.ts"}}),
    assistant({"type": "tool_use", "name": "Grep", "input": {"path": "src"}}),
]


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self.path = write_jsonl(RECORDS, broken=True)
        self.addCleanup(os.unlink, self.path)

    def test_turns_are_text_only_and_merged(self):
        turns, _ = transcript.read(self.path)
        self.assertEqual([t.role for t in turns], ["user", "assistant", "user"])
        self.assertEqual(turns[0].text, "first question")
        self.assertEqual(turns[1].text, "Let me look.\nThe login checks the password.")
        self.assertEqual(turns[2].text, "second question")

    def test_files_dedup_most_recent_last(self):
        _, files = transcript.read(self.path)
        self.assertEqual(files, ["src/auth/login.ts", "src"])

    def test_recent_and_last_reply(self):
        turns, _ = transcript.read(self.path)
        self.assertEqual(len(transcript.recent(turns, 2)), 2)
        self.assertEqual(len(transcript.recent(turns, -1)), 3)
        self.assertEqual(transcript.recent(turns, 0), [])
        self.assertEqual(transcript.last_reply(turns), "Let me look.\nThe login checks the password.")

    def test_missing_file(self):
        self.assertEqual(transcript.read("/no/such/file.jsonl"), ([], []))
        self.assertEqual(transcript.read(None), ([], []))
