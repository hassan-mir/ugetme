import unittest

from ugetme.markers import clean_request, protect, restore, strip_marker

TRACE = ("Traceback (most recent call last):\n"
         '  File "app.py", line 3, in <module>\n    main()\n'
         '  File "app.py", line 2, in main\n    raise ValueError("x")\nValueError: x')


class MarkerTest(unittest.TestCase):
    def test_marker_at_start_or_end(self):
        self.assertEqual(strip_marker("<< hello there"), (True, "hello there"))
        self.assertEqual(strip_marker("<<hello there"), (True, "hello there"))
        self.assertEqual(strip_marker("hello there <<"), (True, "hello there"))

    def test_non_markers(self):
        self.assertFalse(strip_marker("a << b")[0])
        self.assertFalse(strip_marker("<<<triple")[0])
        for heredoc in ("<<EOF\nline\nEOF", "<<eof\nline\neof", "<< EOF\nline\nEOF", "<<-'END'\nx\nEND"):
            self.assertFalse(strip_marker(heredoc)[0], heredoc)

    def test_clean_request(self):
        self.assertEqual(clean_request("<< so um fix the login"), "so um fix the login")
        self.assertEqual(clean_request("so um fix the login <<"), "so um fix the login")
        self.assertIsNone(clean_request("so um fix the login"))
        self.assertIsNone(clean_request("/compact <<"))
        self.assertIsNone(clean_request("!ls <<"))
        self.assertIsNone(clean_request("<<"))

    def test_protect_restore_round_trip(self):
        text = "look at this\n" + TRACE + "\nand this ```a = {1: 2}``` thanks"
        masked, blocks = protect(text)
        self.assertNotIn("Traceback", masked)
        self.assertNotIn("a = {1: 2}", masked)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(restore(masked, blocks), text)

    def test_restore_adds_dropped_blocks_and_ignores_unknown(self):
        _, blocks = protect("see\n" + TRACE)
        self.assertEqual(restore("See the log. ⟦ugetme:9⟧", blocks), "See the log.\n\n" + blocks[0])
        self.assertTrue(restore("x", blocks).endswith("ValueError: x"))

    def test_restore_short_labels(self):
        masked, blocks = protect("see\n" + TRACE)
        self.assertIn("[pasted block: 6 lines]", restore(masked, blocks, short=True))

    def test_single_code_line_is_not_protected(self):
        self.assertEqual(protect("run    npm test please")[1], [])

    def test_common_log_formats_are_protected(self):
        samples = [
            "2026-09-24 12:00:01 ERROR [main] Connection refused to db on port 5432\n"
            "2026-09-24 12:00:02 WARN [main] Retrying the connection in five seconds now",
            'Exception in thread "main" java.lang.NullPointerException: user is null\n'
            "\tat com.app.Main.run(Main.java:12)",
            "error[E0308]: mismatched types in the call to the parse function here\n"
            " --> src/main.rs:4:18",
            "npm ERR! code ERESOLVE could not resolve the dependency tree for the app\n"
            "npm ERR! peer react@18 is required by the component package you added",
            "src/app.ts:12:5 - error TS2322: Type string is not assignable to number\n"
            "src/app.ts:20:1 - error TS2304: Cannot find name foo in this file here",
        ]
        for log in samples:
            self.assertEqual(len(protect("so why does this happen\n" + log)[1]), 1, log)
