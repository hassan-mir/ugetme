import io
import json
import os
import re
from unittest import mock

from helpers import ServerTest, TempHomeTest

from ugetme import hook, output, vocab

DICTATED = "so um can you like ask nimbis to review the the login change today"
CLEAN = "Ask Nimbus to review the login change today, and then deploy it to the staging server before lunch."


def event(prompt, session="s1", cwd=""):
    return {"prompt": prompt, "session_id": session, "cwd": cwd, "transcript_path": ""}


class HookTest(ServerTest):
    def setUp(self):
        super().setUp()
        self.fake_output(CLEAN, [("nimbis", "Nimbus")])

    def block(self):
        return hook.prompt(event("<< " + DICTATED))

    def test_plain_prompt_passes_and_sends_context(self):
        proj = self.home / "proj"
        proj.mkdir()
        self.assertIsNone(hook.prompt(event("please run the tests", cwd=str(proj))))
        self.assertEqual(self.service.live["cwd"], str(proj))

    def test_marker_blocks_with_clean_text(self):
        out = self.block()
        self.assertEqual(out["decision"], "block")
        self.assertTrue(out["hookSpecificOutput"]["suppressOriginalPrompt"])
        self.assertTrue(out["reason"].startswith("✦ ugetme · check ("))
        self.assertIn("\n  nimbis → Nimbus\n", out["reason"])
        self.assertIn(CLEAN, re.sub(r"\x1b\[[0-9;]*m", "", out["reason"]))  # the text is coloured
        self.assertIn(output.FOOTER_NO_CLIPBOARD, out["reason"])

    def test_y_sends_the_clean_text(self):
        self.block()
        ctx = hook.prompt(event("Yes."))["hookSpecificOutput"]["additionalContext"]
        self.assertIn(CLEAN, ctx)
        self.assertIn("confirmed", ctx)

    def test_short_reply_goes_to_the_agent(self):
        self.block()
        ctx = hook.prompt(event("no, nimbis is right"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("- nimbis → Nimbus", ctx)
        self.assertIn("keep '<word>'", ctx)
        self.assertIn("not about ugetme's check", ctx)
        self.assertNotIn("->", ctx)

    def test_paste_back_with_an_edit_learns(self):
        self.block()
        out = hook.prompt(event(CLEAN.replace("Nimbus", "NimbusHQ")))
        self.assertTrue(out["systemMessage"].startswith("✦ ugetme learned: Nimbus → NimbusHQ"))
        self.assertEqual(vocab.load(self.home / "vocab.md").terms[0].term, "NimbusHQ")

    def test_long_new_prompt_after_a_check_is_not_a_reply(self):
        self.block()
        self.assertIsNone(hook.prompt(event(
            "please write the release notes for version two of the app with all the new features we added this month")))

    def test_sensor_learns_from_an_edited_handy_paste(self):
        self.call("POST", "/v1/chat/completions", {"messages": [{"role": "user", "content": DICTATED}]})
        out = hook.prompt(event(CLEAN.replace("Nimbus", "NimbusHQ")))
        self.assertIn("learned: Nimbus → NimbusHQ", out["systemMessage"])

    def test_sensor_ignores_an_unedited_paste(self):
        self.call("POST", "/v1/chat/completions", {"messages": [{"role": "user", "content": DICTATED}]})
        self.assertIsNone(hook.prompt(event(CLEAN)))

    def test_context_from_a_session_with_env_credentials_is_refused(self):
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "other-account"
        self.addCleanup(os.environ.pop, "CLAUDE_CODE_OAUTH_TOKEN", None)
        hook.prompt(event("please run the tests", cwd=str(self.home)))
        self.assertIsNone(self.service.live)

    def test_commands_and_inner_calls_pass(self):
        self.assertIsNone(hook.prompt(event("/compact <<")))
        os.environ["UGETME_INNER"] = "1"
        self.assertIsNone(hook.prompt(event("<< " + DICTATED)))

    def test_engine_failure_blocks_without_sending(self):
        os.environ["FAKE_CLAUDE_MODE"] = "fail"
        out = self.block()
        self.assertEqual(out["decision"], "block")
        self.assertIn("could not clean", out["reason"])

    def test_service_error_blocks_a_marked_prompt_and_lets_a_checked_one_through(self):
        with mock.patch.object(hook.client, "clean", side_effect=hook.client.ClientError("service answered 500")):
            self.assertIn("service answered 500", self.block()["reason"])
            self.set_config(mode="check")
            out = hook.prompt(event(DICTATED, session="s2"))
        self.assertNotIn("decision", out)
        self.assertIn("service answered 500", out["systemMessage"])

    def test_check_mode_checks_a_prompt_without_the_marker(self):
        self.set_config(mode="check")
        out = hook.prompt(event(DICTATED))
        self.assertEqual(out["decision"], "block")
        self.assertIn("\n  nimbis → Nimbus\n", out["reason"])
        ctx = hook.prompt(event("y"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn(CLEAN, ctx)

    def test_check_mode_skips_short_prompts_and_commands(self):
        self.set_config(mode="check")
        for prompt in ("run the tests", "/ugetme status please now ok", "!ls -la the folder now"):
            self.assertIsNone(hook.prompt(event(prompt)), prompt)

    def test_check_mode_failure_lets_the_prompt_through(self):
        self.set_config(mode="check")
        os.environ["FAKE_CLAUDE_MODE"] = "fail"
        out = hook.prompt(event(DICTATED))
        self.assertNotIn("decision", out)
        self.assertIn("sent as you wrote it", out["systemMessage"])

    def test_check_mode_sends_an_edit_of_the_check(self):
        self.set_config(mode="check")
        log = self.fake_log()
        hook.prompt(event(DICTATED))
        edit = CLEAN.replace("Nimbus", "NimbusHQ").replace("before lunch", "after the standup meeting with the team")
        self.assertEqual(hook.prompt(event(edit)), output.learned([("Nimbus", "NimbusHQ")]))
        self.assertEqual(len(self.fake_calls(log)), 1)  # the edit is not checked again

    def test_check_mode_reply_to_a_check_goes_to_the_agent(self):
        self.set_config(mode="check")
        log = self.fake_log()
        hook.prompt(event(DICTATED))
        ctx = hook.prompt(event("no, nimbis is the right name here"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("answers ugetme's check", ctx)
        self.assertEqual(len(self.fake_calls(log)), 1)

    def test_other_modes_check_only_with_the_marker(self):
        for mode in ("auto", "manual"):
            self.set_config(mode=mode)
            self.assertIsNone(hook.prompt(event(DICTATED, session=mode)))

    def test_run_never_crashes(self):
        with mock.patch("sys.stdin", io.StringIO("not json")), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(hook.run("prompt"), 0)
        self.assertEqual(out.getvalue(), "")
        with mock.patch.object(hook, "prompt", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stdin", io.StringIO(json.dumps({"prompt": "<< fix it now"}))), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(hook.run("prompt"), 0)
        self.assertIn("could not clean", out.getvalue())
        with mock.patch.object(hook, "prompt", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stdin", io.StringIO(json.dumps({"prompt": DICTATED}))), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(hook.run("prompt"), 0)
        self.assertEqual(out.getvalue(), "")  # without <<, the prompt goes through


class HookNoServiceTest(TempHomeTest):
    def test_marker_without_service_blocks(self):
        with mock.patch.object(hook.client, "ensure_running", return_value=False):
            out = hook.prompt(event("<< " + DICTATED))
        self.assertEqual(out["decision"], "block")
        self.assertIn("not running", out["reason"])
        self.assertIn(str(self.home / "serve.log"), out["reason"])
        self.assertNotIn("ugetme serve", out["reason"])

    def test_check_mode_without_service_waits_briefly_and_sends(self):
        self.set_config(mode="check")
        with mock.patch.object(hook.client, "ensure_running", return_value=False) as ensure:
            out = hook.prompt(event(DICTATED))
        self.assertNotIn("decision", out)
        self.assertIn("not running", out["systemMessage"])
        self.assertLessEqual(ensure.call_args.kwargs["wait_s"], 2.0)

    def test_first_session_saves_its_login(self):
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.home / "login2")
        with mock.patch.object(hook.client, "ensure_running", return_value=True):
            hook.session_start({})
        from ugetme import config
        cfg = config.load()
        self.assertEqual(cfg["claude_config_dir"], str(self.home / "login2"))
        self.assertEqual(cfg["env_path"], os.environ["PATH"])
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.home / "login3")
        with mock.patch.object(hook.client, "ensure_running", return_value=True):
            hook.session_start({})
        self.assertEqual(config.load()["claude_config_dir"], str(self.home / "login2"))

    def test_hook_budget_fits_the_timeout(self):
        from pathlib import Path
        from ugetme import client, clipboard, config
        hooks = json.loads((Path(__file__).resolve().parents[1] / "hooks" / "hooks.json").read_text())
        prompt_hook = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        worst = 8 + config.MAX_TIMEOUT_S + client.REQUEST_MARGIN_S + clipboard.TOTAL_TIMEOUT_S + 2
        self.assertLess(worst, prompt_hook["timeout"])
        self.assertIn("|| python ", prompt_hook["command"])
        for event_name, arg in (("UserPromptSubmit", "prompt"), ("SessionStart", "session-start")):
            command = hooks["hooks"][event_name][0]["hooks"][0]["command"]
            self.assertTrue(command.startswith(f"ugetme hook {arg} || python3 "), command)  # the installed ugetme first, then the plugin's bin/ugetme
            self.assertTrue(command.endswith("|| true"), command)  # a missing file must never block a prompt (exit 2)

    def test_plain_prompt_without_service_passes(self):
        self.assertIsNone(hook.prompt(event("please run the tests for the login page and then tell me")))


class CheckHighlightTest(TempHomeTest):
    CHANGES = [("nimbis", "Nimbus")]
    VIEW = "Can you check the Nimbus onboarding flow for Nimbus-api users?"

    def test_fixed_words_are_white_in_yellow_text(self):
        reason = output.block(self.VIEW, "raw words", None, True, self.CHANGES)["reason"]
        self.assertIn("\x1b[33mCan you check the \x1b[1;97mNimbus\x1b[0m\x1b[33m onboarding", reason)
        self.assertEqual(reason.count("\x1b[1;97mNimbus\x1b[0m"), 1)  # "Nimbus-api" is another word
        self.assertTrue(reason.rstrip().endswith(output.FOOTER))  # the footer stays plain

    def test_inverse_and_none(self):
        self.set_config(check_highlight="inverse")
        self.assertIn("\x1b[7mNimbus\x1b[27m", output.block(self.VIEW, "raw", None, True, self.CHANGES)["reason"])
        self.set_config(check_highlight="none")
        self.assertNotIn("\x1b[", output.block(self.VIEW, "raw", None, True, self.CHANGES)["reason"])
