import json
import os
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from helpers import CLOSED_PORT, TempHomeTest

from ugetme import engine

CFG = {"engine": "claude", "model": "sonnet", "effort": "low", "timeout_s": 3, "claude_bin": "",
       "claude_config_dir": "", "engine_env": {}, "env_path": "", "openai": {"base_url": "", "api_key": "", "model": ""}}


class ClaudeEngineTest(TempHomeTest):
    def test_success_and_isolation_flags(self):
        log = self.fake_log()
        self.assertEqual(engine.run("<raw_prompt>\nhi\n</raw_prompt>", CFG).clean, "Clean text.")
        call = self.fake_calls(log)[0]
        argv = call["argv"]
        self.assertEqual(argv[:3], ["-p", "--model", "sonnet"])
        for flag in ("--system-prompt-file", "--tools", "--no-session-persistence", "--setting-sources", "--effort",
                     "--strict-mcp-config"):   # no MCP servers: ugetme uses no tools, and starting them made cleanups slower
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "")
        self.assertNotIn("--bare", argv)  # --bare never reads the OAuth login, so the user's Claude login would not work
        self.assertEqual((call["inner"], call["no_mds"]), ("1", "1"))

    def test_system_prompt_goes_through_a_file(self):
        log = self.fake_log()
        engine.run("x", CFG)
        call = self.fake_calls(log)[0]
        self.assertEqual(call["system_prompt"], engine.SYSTEM_PROMPT)
        self.assertNotIn("--system-prompt", call["argv"])

    def test_session_credentials_are_not_inherited(self):
        log = self.fake_log()
        os.environ.update({"ANTHROPIC_API_KEY": "k", "CLAUDE_CODE_OAUTH_TOKEN": "t", "CLAUDECODE": "1"})
        engine.run("x", CFG)
        self.assertEqual(self.fake_calls(log)[0]["creds"], [])

    def test_engine_env_and_path_from_config(self):
        log = self.fake_log()
        engine.run("x", dict(CFG, engine_env={"ANTHROPIC_BASE_URL": "http://gateway"}, env_path="/opt/node/bin"))
        call = self.fake_calls(log)[0]
        self.assertEqual(call["base_url"], "http://gateway")
        self.assertTrue(call["path"].startswith("/opt/node/bin" + os.pathsep))

    def test_windows_hides_the_console(self):
        done = mock.Mock(returncode=0, stdout='{"clean": "a"}', stderr="")
        with mock.patch.dict(engine.config.NO_WINDOW, creationflags=0x08000000), mock.patch.object(engine.subprocess, "run", return_value=done) as run:
            engine.run("x", CFG)
        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)

    def test_session_login_is_not_inherited(self):
        log = self.fake_log()
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.home / "some-session-login")
        engine.run("x", CFG)
        self.assertIsNone(self.fake_calls(log)[0]["config_dir"])

    def test_configured_login_is_used(self):
        log = self.fake_log()
        engine.run("x", dict(CFG, claude_config_dir=str(self.home / "login-b")))
        self.assertEqual(self.fake_calls(log)[0]["config_dir"], str(self.home / "login-b"))

    def test_not_logged_in_names_the_login_and_the_next_step(self):
        os.environ["FAKE_CLAUDE_MODE"] = "fail"
        with self.assertRaises(engine.CleanupError) as e:
            engine.run("x", dict(CFG, claude_config_dir="/logins/work"))
        self.assertIn("/logins/work is not logged in", str(e.exception))
        self.assertIn("run claude, then type /login", str(e.exception))

    def test_unreachable_provider_says_what_to_check(self):
        url = f"http://127.0.0.1:{CLOSED_PORT}/v1"
        cfg = dict(CFG, engine="openai", openai={"base_url": url, "api_key": "", "model": "m"})
        with self.assertRaises(engine.CleanupError) as e:
            engine.run("x", cfg)
        self.assertEqual(str(e.exception), f"cannot reach {url}. Is your model server running?")

    def test_retries_without_effort(self):
        log = self.fake_log()
        os.environ["FAKE_CLAUDE_MODE"] = "reject_effort"
        self.assertEqual(engine.run("x", CFG).clean, "Clean text.")
        self.assertNotIn("--effort", self.fake_calls(log)[1]["argv"])

    def test_failures_raise_cleanup_error(self):
        for mode, fragment, timeout_s in (("fail", "not logged in", 3), ("garbage", "no JSON", 3), ("sleep", "timed out", 1)):
            os.environ["FAKE_CLAUDE_MODE"] = mode
            with self.assertRaises(engine.CleanupError) as ctx:
                engine.run("x", dict(CFG, timeout_s=timeout_s))
            self.assertIn(fragment, str(ctx.exception))

    def test_missing_binary(self):
        os.environ["UGETME_CLAUDE_BIN"] = "/no/such/claude"
        with self.assertRaises(engine.CleanupError) as ctx:
            engine.run("x", CFG)
        self.assertIn("could not start claude", str(ctx.exception))


class ParseTest(unittest.TestCase):
    def test_unclear_changes_and_shell_characters(self):
        r = engine.parse_output(json.dumps({"clean": "a", "changes": [
            {"heard": "nimbis", "meant": "`Nimbus`"}, {"heard": "x", "meant": "x"}, {"heard": 1}, "junk"],
            "unclear": {"heard": "it's", "guess": "$x", "question": "Did you mean x?"}}))
        self.assertEqual(r.changes, [("nimbis", "Nimbus")])
        self.assertEqual((r.unclear["heard"], r.unclear["guess"]), ("its", "x"))

    def test_json_inside_extra_text_and_errors(self):
        self.assertEqual(engine.parse_output('Here:\n{"clean": "b", "unclear": null}\n').clean, "b")
        self.assertEqual(engine.parse_output('{"clean": "a", "changes": "bad"}').changes, [])
        with self.assertRaises(engine.CleanupError):
            engine.parse_output('{"clean": "  "}')

    def test_system_prompt_rules(self):
        for phrase in ("numbered list", "bullet list", "Markdown table", "talks about as a word", "⟦ugetme:1⟧", "# Keep",
                       "Never put names of projects, products or people in backticks", "Keep the user's tone",
                       "Do not repeat the contents of a list or table", "spells a word letter by letter",
                       "drop the letters"):
            self.assertIn(phrase, engine.SYSTEM_PROMPT)

    def test_system_prompt_has_no_example_names(self):
        # A name in an example leaks into the output.
        for name in ("Nimbus", "nimbis", "Handy", "Wispr"):
            self.assertNotIn(name, engine.SYSTEM_PROMPT)
        self.assertIn("Never take a word from the examples in these rules", engine.SYSTEM_PROMPT)


class FakeProvider(BaseHTTPRequestHandler):
    calls = []
    status = 200
    reply = {"choices": [{"message": {"content": json.dumps({"clean": "Clean text.", "changes": [], "unclear": None})}}]}

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeProvider.calls.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        data = json.dumps(FakeProvider.reply).encode()
        self.send_response(FakeProvider.status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class OpenAIEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        FakeProvider.calls.clear()
        FakeProvider.status = 200

    def cfg(self, **openai):
        return dict(CFG, engine="openai", openai=dict({"base_url": self.url, "api_key": "", "model": "llama3"}, **openai))

    def test_sends_system_prompt_model_and_key(self):
        self.assertEqual(engine.run("input text", self.cfg(api_key="k")).clean, "Clean text.")
        call = FakeProvider.calls[0]
        self.assertEqual(call["path"], "/v1/chat/completions")
        self.assertEqual(call["auth"], "Bearer k")
        self.assertEqual(call["body"]["model"], "llama3")
        self.assertEqual(call["body"]["temperature"], 0)
        self.assertEqual(call["body"]["messages"][0], {"role": "system", "content": engine.SYSTEM_PROMPT})
        self.assertEqual(call["body"]["messages"][1], {"role": "user", "content": "input text"})

    def test_no_key_sends_no_auth(self):
        engine.run("x", self.cfg())
        self.assertIsNone(FakeProvider.calls[0]["auth"])

    def test_errors(self):
        FakeProvider.status = 500
        with self.assertRaises(engine.CleanupError) as ctx:
            engine.run("x", self.cfg())
        self.assertIn("provider returned 500", str(ctx.exception))
        with self.assertRaises(engine.CleanupError) as ctx:
            engine.run("x", self.cfg(base_url=""))
        self.assertIn("openai.base_url is not set", str(ctx.exception))

