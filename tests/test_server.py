import json
import os
from unittest import mock

from helpers import ServerTest

from ugetme import server, vocab

DICTATED = "so um can you like ask nimbis to review the the login change today"
CLEAN = "Ask Nimbus to review the login change today."
HANDY_PROMPT = "<transcript>\n{}\n</transcript>\n\nThe above is a transcript. Clean it by:\n1. Fix spelling"


class ServerTestCase(ServerTest):
    def setUp(self):
        super().setUp()
        self.fake_output(CLEAN, [("nimbis", "Nimbus")])

    def chat(self, content, **extra):
        body = {"model": "ugetme", "messages": [{"role": "system", "content": "ignored system text"},
                                                {"role": "user", "content": content}]}
        body.update(extra)
        return self.call("POST", "/v1/chat/completions", body, raw=bool(extra.get("stream")))

    def engine_input(self, content=DICTATED) -> str:
        """What the engine reads for one chat request."""
        log = self.fake_log()
        self.chat(content)
        return self.fake_calls(log)[0]["stdin"]

    def context(self, cwd, config_dir="", **extra) -> dict:
        body = dict({"cwd": str(cwd), "transcript_path": "", "config_dir": config_dir}, **extra)
        return self.call("POST", "/ugetme/context", body)[1]

    def test_health_needs_no_token(self):
        status, body = self.call("GET", "/health", auth=False)
        self.assertEqual((status, body["ok"], body["pid"]), (200, True, os.getpid()))

    def test_other_endpoints_need_the_token(self):
        self.assertEqual(self.call("GET", "/v1/models", auth=False)[0], 401)
        self.assertEqual(self.call("POST", "/v1/chat/completions", {"messages": []}, auth=False)[0], 401)
        self.assertEqual(self.call("GET", "/ugetme/recent", auth=False)[0], 401)

    def test_cors_preflight_is_refused(self):
        self.assertEqual(self.call("OPTIONS", "/v1/chat/completions", auth=False)[0], 403)

    def test_models(self):
        status, body = self.call("GET", "/v1/models")
        self.assertEqual(body["data"][0]["id"], "ugetme")

    def test_chat_returns_clean_text(self):
        status, body = self.chat(DICTATED)
        self.assertEqual((status, body["object"]), (200, "chat.completion"))
        self.assertEqual(body["choices"][0]["message"]["content"], CLEAN)

    def test_handy_default_prompt_sends_only_the_transcript(self):
        stdin = self.engine_input(HANDY_PROMPT.format(DICTATED))
        self.assertIn(DICTATED, stdin)
        self.assertNotIn("Fix spelling", stdin)
        self.assertNotIn("ignored system text", stdin)

    def test_content_parts_are_read(self):
        status, body = self.chat([{"type": "text", "text": DICTATED}])
        self.assertEqual(body["choices"][0]["message"]["content"], CLEAN)

    def test_stream(self):
        status, text = self.chat(DICTATED, stream=True)
        self.assertEqual(status, 200)
        first = json.loads(text.split("\n\n")[0][len("data: "):])
        self.assertEqual(first["object"], "chat.completion.chunk")
        self.assertEqual(first["choices"][0]["delta"]["content"], CLEAN)
        self.assertTrue(text.endswith("data: [DONE]\n\n"))

    def test_failure_returns_the_raw_text(self):
        os.environ["FAKE_CLAUDE_MODE"] = "fail"
        status, body = self.chat(DICTATED)
        self.assertEqual((status, body["choices"][0]["message"]["content"]), (200, DICTATED))

    def test_empty_text_skips_the_engine(self):
        log = self.fake_log()
        status, body = self.chat("   ")
        self.assertEqual(body["choices"][0]["message"]["content"], "")
        self.assertEqual(self.fake_calls(log), [])

    def test_bad_json_body(self):
        self.assertEqual(self.call("POST", "/ugetme/clean", None)[0], 400)

    def test_live_context_from_the_same_login_is_used(self):
        proj = self.home / "proj"
        (proj / "src").mkdir(parents=True)
        self.assertTrue(self.context(proj)["accepted"])
        self.assertIn("<project>\nproj: src/", self.engine_input())

    def test_live_context_from_other_login_is_refused(self):
        proj = self.home / "proj"
        proj.mkdir()
        self.assertFalse(self.context(proj, str(self.home / "other"))["accepted"])
        self.assertNotIn("<project>", self.engine_input())

    def test_live_context_from_a_trusted_login_is_used(self):
        other = self.home / "other"
        self.set_config(trusted_logins=[str(other)])
        proj = self.home / "proj"
        (proj / "src").mkdir(parents=True)
        self.assertTrue(self.context(proj, str(other))["accepted"])
        self.assertIn("<project>\nproj: src/", self.engine_input())

    def test_old_live_context_is_used_by_default(self):
        proj = self.home / "proj"
        (proj / "src").mkdir(parents=True)
        self.context(proj)
        self.service.live["ts"] -= 3 * 24 * 3600
        self.assertIn("<project>", self.engine_input())

    def test_live_context_older_than_the_limit_is_ignored(self):
        self.set_config(live_context_minutes=30)
        proj = self.home / "proj"
        proj.mkdir()
        self.context(proj)
        self.service.live["ts"] -= 31 * 60
        self.assertNotIn("<project>", self.engine_input())

    def test_clean_endpoint_and_recent(self):
        status, body = self.call("POST", "/ugetme/clean", {"text": DICTATED})
        self.assertEqual((body["clean"], body["changes"], body["failed"]), (CLEAN, [["nimbis", "Nimbus"]], ""))
        status, recent = self.call("GET", "/ugetme/recent")
        self.assertEqual(recent["outputs"][0]["id"], body["id"])

    def test_learn_from_an_edit(self):
        _, body = self.call("POST", "/ugetme/clean", {"text": DICTATED})
        _, res = self.call("POST", "/ugetme/learn",
                           {"output_id": body["id"], "sent": CLEAN.replace("Nimbus", "NimbusHQ")})
        self.assertEqual(res["learned"], [["Nimbus", "NimbusHQ"]])
        self.assertEqual(vocab.load(self.home / "vocab.md").terms[0].term, "NimbusHQ")

    def test_the_raw_text_sent_again_teaches_nothing(self):
        raw = "please ask Nimbis to review the login change today"
        self.fake_output("Please ask Nimbus to review the login change today.")
        _, body = self.call("POST", "/ugetme/clean", {"text": raw})
        _, res = self.call("POST", "/ugetme/learn", {"output_id": body["id"], "sent": raw})
        self.assertEqual(res["learned"], [])

    def test_an_edit_is_learned_when_the_cleanup_changed_only_punctuation(self):
        raw = "Ask Nimbus to review it today please"
        self.fake_output(raw + ".")
        _, body = self.call("POST", "/ugetme/clean", {"text": raw})
        _, res = self.call("POST", "/ugetme/learn",
                           {"output_id": body["id"], "sent": "Ask NimbusHQ to review it today please."})
        self.assertEqual(res["learned"], [["Nimbus", "NimbusHQ"]])

    def test_the_engine_login_is_never_trusted_past_the_account_check(self):
        self.set_config(trusted_logins=[str(self.home / "engine")], claude_config_dir=str(self.home / "engine"))
        self.assertFalse(self.context(self.home, str(self.home / "engine"), auth="abcd")["accepted"])

    def test_correction_protects_a_recent_change(self):
        self.call("POST", "/ugetme/clean", {"text": DICTATED})
        (self.home / "vocab.md").write_text('# Terms\n- Nimbus (heard: "nimbis")\n')
        stdin = self.engine_input("no, nimbis was right, it is a different app so please leave it")
        self.assertIn("# Keep\n- nimbis", stdin)

    def test_config_changes_apply_without_restart(self):
        self.set_config(model="haiku")
        log = self.fake_log()
        self.chat(DICTATED)
        argv = self.fake_calls(log)[0]["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "haiku")

    def test_unexpected_errors_return_the_raw_text(self):
        with mock.patch.object(server.clean, "clean_text", side_effect=RuntimeError("boom")):
            status, body = self.chat(DICTATED)
        self.assertEqual((status, body["choices"][0]["message"]["content"]), (200, DICTATED))

    def test_bad_bytes_in_a_project_vocabulary_are_tolerated(self):
        proj = self.home / "proj"
        (proj / ".claude").mkdir(parents=True)
        (proj / ".claude" / "ugetme.md").write_bytes(b"\xff\xfe# Terms\n- Orbit\n")
        self.context(proj)
        status, body = self.chat(DICTATED)
        self.assertEqual(body["choices"][0]["message"]["content"], CLEAN)

    def test_a_new_token_works_without_restart(self):
        (self.home / "token").write_text("second-token-value")
        self.assertEqual(self.call("GET", "/v1/models")[0], 200)

    def test_session_with_env_credentials_is_refused(self):
        self.assertFalse(self.context(self.home, auth="abcd")["accepted"])

    def test_windows_does_not_reuse_ports(self):
        with mock.patch.object(server.sys, "platform", "win32"):
            httpd, _ = server.make_server(self.cfg, port=0)
        self.addCleanup(httpd.server_close)
        self.assertFalse(httpd.allow_reuse_address)

    def test_extract_text(self):
        self.assertEqual(server.extract_text([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]), "a")
        self.assertEqual(server.extract_text("junk"), "")
        upper = [{"role": "user", "content": "\n<TRANSCRIPT>\n so um hi \n</TRANSCRIPT>"}]
        self.assertEqual(server.extract_text(upper), "so um hi")

    def test_second_server_on_the_same_port_fails(self):
        with self.assertRaises(server.PortInUse):
            server.make_server(self.cfg)
