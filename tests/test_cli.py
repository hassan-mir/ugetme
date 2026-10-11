import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock

from helpers import TempHomeTest

from ugetme import __version__, cli, config, state, vocab, wizard

SKIP = ["--no-scan", "--no-autostart", "--no-handy", "--no-test"]
OPENAI = ["--engine", "openai", "--openai-url", "http://h/v1", "--openai-model", "m"]
HANDY_ONLY = ["--yes", "--engine", "claude", "--login", "", "--no-scan", "--no-autostart", "--handy", "--no-test"]


def run_cli(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(list(args))
    return code, out.getvalue()


class CliTest(TempHomeTest):
    def test_learn_keep_forget_style_tidy(self):
        self.assertEqual(run_cli("learn", "cloud", "code", "->", "Claude", "Code")[1].strip(),
                         'ugetme learned: "cloud code" → Claude Code')
        self.assertEqual(run_cli("learn", "orbits", "Orbit")[1].strip(), 'ugetme learned: "orbits" → Orbit')
        self.assertEqual(run_cli("keep", "nimby")[1].strip(), "ugetme keeps: nimby")
        self.assertEqual(run_cli("forget", "Orbit")[1].strip(), "ugetme forgot: Orbit")
        self.assertEqual(run_cli("forget", "Orbit"), (1, "ugetme does not know: Orbit\n"))
        run_cli("style", "Prefer", "numbered", "lists.")
        self.assertIn("tidied", run_cli("tidy")[1])
        v = vocab.load(self.home / "vocab.md")
        self.assertEqual(([e.term for e in v.terms], v.keep, v.style), (["Claude Code"], ["nimby"], ["Prefer numbered lists."]))

    def test_review_without_a_terminal_does_not_crash(self):
        state.log({"event": "cleaned", "id": "a1", "raw": "x", "clean": "y", "changes": [["nimbis", "Nimbus"]]})
        code, out = run_cli("review")
        self.assertEqual(code, 0)
        self.assertIn("1. nimbis → Nimbus", out)
        self.assertIn("ugetme review --wrong", out)

    def test_stop_reports_a_service_that_did_not_stop(self):
        with mock.patch.object(cli.client, "stop", return_value=None):
            self.assertEqual(run_cli("stop")[1].strip(), "ugetme was not running")
        with mock.patch.object(cli.client, "stop", return_value=False):
            code, out = run_cli("stop")
        self.assertEqual((code, out.strip()), (1, "ugetme did not stop"))

    def test_status_warns_about_an_older_service(self):
        with mock.patch.object(cli.client, "health", return_value={"ok": True, "version": "0.0.1", "pid": 7}):
            out = run_cli("status")[1]
        self.assertIn("running (pid 7) · version 0.0.1", out)
        self.assertIn("run: ugetme restart", out)

    def test_restart(self):
        with mock.patch.object(cli.client, "stop", return_value=True), \
                mock.patch.object(cli.client, "ensure_running", return_value=True) as ensure:
            code, out = run_cli("restart")
        self.assertEqual((code, out.strip()), (0, f"ugetme restarted ({__version__})"))
        ensure.assert_called_once()
        with mock.patch.object(cli.client, "stop", return_value=False):
            self.assertEqual(run_cli("restart")[0], 1)

    def test_clipboard_command(self):
        with mock.patch.object(cli.clipboard, "paste", return_value="so um hi"), \
                mock.patch.object(cli.clipboard, "copy", return_value=True) as copy, \
                mock.patch.object(cli.client, "ensure_running", return_value=True), \
                mock.patch.object(cli.client, "request", return_value={"clean": "Hi.", "changes": []}):
            code, out = run_cli("clipboard")
        self.assertEqual((code, out.strip()), (0, "Hi."))
        copy.assert_called_once_with("Hi.")

    def test_clipboard_command_keeps_the_text_when_cleanup_fails(self):
        with mock.patch.object(cli.clipboard, "paste", return_value="so um hi"), \
                mock.patch.object(cli.clipboard, "copy") as copy, \
                mock.patch.object(cli.client, "ensure_running", return_value=True), \
                mock.patch.object(cli.client, "request", return_value={"clean": "so um hi", "failed": "timeout"}):
            self.assertEqual(run_cli("clipboard")[0], 1)
        copy.assert_not_called()
        with mock.patch.object(cli.clipboard, "paste", return_value=""):
            self.assertEqual(run_cli("clipboard")[0], 1)

    def test_test_and_clean_exit_1_when_the_cleanup_fails(self):
        failed = {"clean": "so um hi", "failed": "claude login ~/.claude is not logged in"}
        with mock.patch.object(cli.client, "ensure_running", return_value=True), \
                mock.patch.object(cli.client, "request", return_value=failed):
            self.assertEqual(run_cli("test")[0], 1)
            self.assertEqual(run_cli("clean", "so um hi")[0], 1)

    def test_forget_accepts_the_heard_word(self):
        run_cli("learn", "nimbis", "Nimbus")
        code, out = run_cli("forget", "nimbis")
        self.assertEqual((code, out.strip()), (0, "ugetme forgot: Nimbus"))

    def test_unknown_command_suggests_the_closest(self):
        code, out = run_cli("stauts")
        self.assertEqual(code, 2)
        self.assertIn("unknown command 'stauts'. Did you mean status?", out)

    def test_help_after_a_command_shows_usage(self):
        with mock.patch.object(cli.client, "request") as request:
            code, out = run_cli("clean", "--help")
        request.assert_not_called()
        self.assertIn("usage: ugetme", out)

    def test_clipboard_check_reads_nothing(self):
        with mock.patch.object(cli.clipboard, "tool", return_value="xclip"), \
                mock.patch.object(cli.clipboard, "paste") as paste, mock.patch.object(cli.clipboard, "copy") as copy:
            code, out = run_cli("clipboard", "--check")
        self.assertEqual((code, out.strip()), (0, "clipboard tool: xclip"))
        paste.assert_not_called()
        copy.assert_not_called()
        with mock.patch.object(cli.clipboard, "tool", return_value=None):
            code, out = run_cli("clipboard", "--check")
        self.assertEqual(code, 1)
        self.assertIn("No clipboard tool found", out)

    def test_clipboard_without_a_tool(self):
        with mock.patch.object(cli.clipboard, "paste", return_value=None):
            code, out = run_cli("clipboard")
        self.assertEqual(code, 1)
        self.assertIn("No clipboard tool found", out)

    def test_status_for_the_openai_engine_hides_the_claude_model(self):
        self.set_config(engine="openai", openai={"base_url": "http://h/v1", "api_key": "", "model": "m"})
        out = run_cli("status")[1]
        self.assertIn("engine: openai · http://h/v1 · m", out)
        self.assertNotIn("sonnet", out)

    def test_config_lists_gets_and_sets(self):
        code, out = run_cli("config")
        self.assertEqual(code, 0)
        self.assertIn("model = sonnet", out)
        self.assertIn("context = balanced  (none, light, balanced, full, custom)", out)
        self.assertEqual(run_cli("config", "model")[1].strip(), "sonnet")
        self.assertEqual(run_cli("config", "model", "opus")[0], 0)
        self.assertEqual(config.load()["model"], "opus")
        run_cli("config", "custom.turns", "3")
        self.assertEqual(config.load()["custom"]["turns"], 3)
        run_cli("config", "log", "off")
        self.assertIs(config.load()["log"], False)

    def test_config_port_stops_the_old_service_first(self):
        order, old = [], config.load()["port"]
        with mock.patch.object(cli.client, "stop", side_effect=lambda: order.append(("stop", config.load()["port"]))):
            code, out = run_cli("config", "port", "7399")
        self.assertEqual(code, 0)
        self.assertEqual(order, [("stop", old)])   # stopped on the old port, before the change
        self.assertEqual(config.load()["port"], 7399)
        self.assertIn("ugetme ensure", out)

    def test_config_refuses_bad_values(self):
        code, out = run_cli("config", "context", "huge")
        self.assertEqual(code, 1)
        self.assertIn("context must be one of: none, light, balanced, full, custom", out)
        self.assertEqual(run_cli("config", "timeout_s", "soon")[0], 1)
        code, out = run_cli("config", "modell", "opus")
        self.assertEqual(code, 1)
        self.assertIn("Did you mean model?", out)
        code, out = run_cli("config", "trusted_logins", "x")
        self.assertEqual(code, 1)
        self.assertIn("trusted_logins cannot be set here: use ugetme trust", out)
        code, out = run_cli("config", "engine_env", "x")
        self.assertEqual((code, out.strip()), (1, "engine_env cannot be set here: edit ~/.ugetme/config.json"))

    def test_config_does_not_save_a_value_it_refuses(self):
        code, out = run_cli("config", "timeout_s", "9999")
        self.assertEqual(code, 1)
        self.assertIn("was not accepted", out)
        saved = json.loads(config.settings_file().read_text(encoding="utf-8")) if config.settings_file().exists() else {}
        self.assertNotEqual(saved.get("timeout_s"), 9999)

    def test_config_hides_the_folders_in_env_path(self):
        home = os.path.expanduser("~")
        self.set_config(env_path=os.pathsep.join([os.path.join(home, "bin"), "/mnt/c/Users/somebody/bin", "/usr/bin"]))
        for out in (run_cli("config")[1], run_cli("config", "env_path")[1]):
            self.assertNotIn("somebody", out)
            self.assertNotIn(home + os.sep + "bin", out)
        self.assertIn("env_path = (3 folders)", run_cli("config")[1])
        self.set_config(engine_env={"CLAUDE_CONFIG_DIR": os.path.join(home, ".claude-work")})
        self.assertIn("~", run_cli("config", "engine_env")[1])
        self.assertNotIn(home + os.sep, run_cli("config")[1])
        self.assertIn("(file: ~", run_cli("config")[1].replace(os.sep, "/"))

    def test_learn_with_two_quoted_values(self):
        self.assertEqual(run_cli("learn", "cloud code", "Claude Code")[1].strip(), 'ugetme learned: "cloud code" → Claude Code')

    def test_status_shows_paths_in_the_home_folder_with_a_tilde(self):
        home = os.path.expanduser("~")
        self.set_config(claude_config_dir=os.path.join(home, ".claude-work"), trusted_logins=[os.path.join(home, ".claude-other")])
        out = run_cli("status")[1]
        self.assertIn("login: ~/.claude-work", out.replace(os.sep, "/"))
        self.assertIn("trusted logins: ~/.claude-other", out.replace(os.sep, "/"))
        self.assertNotIn(home + os.sep + ".claude", out)

    def test_status_without_the_service(self):
        code, out = run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("service: not running", out)
        self.assertIn("files: ~", out)   # the test HOME is ugetme's folder, shown as ~

    def test_review_list_and_wrong(self):
        state.log({"event": "cleaned", "id": "a1", "raw": "ask nimbis", "clean": "Ask Nimbus",
                   "changes": [["nimbis", "Nimbus"]]})
        code, out = run_cli("review", "--list")
        self.assertEqual(json.loads(out)[0], {"n": 1, "heard": "nimbis", "meant": "Nimbus", "clean": "Ask Nimbus"})
        run_cli("review", "--wrong", "1")
        self.assertEqual(vocab.load(self.home / "vocab.md").keep, ["nimbis"])

    def test_version(self):
        self.assertEqual(run_cli("--version")[1].strip(), __version__)


class WizardTest(TempHomeTest):
    def setUp(self):
        super().setUp()
        (self.home / "handy").mkdir()
        self.handy_file.write_text(json.dumps({"settings": {
            "post_process_providers": [], "bindings": {"transcribe": {"current_binding": "a"},
                                                        "transcribe_with_post_process": {"current_binding": "b"}}}}))

    def run_setup(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = wizard.run(argv)
        return code, out.getvalue()

    def test_setup_with_flags(self):
        (self.home / "code" / "nimbus-api").mkdir(parents=True)
        code = self.run_setup(["--yes", "--engine", "claude", "--login", "", "--scan-root", str(self.home / "code"),
                               "--autostart", "--handy", "--mode", "auto", "--no-handy-auto-submit", "--no-test"])[0]
        self.assertEqual(code, 0)
        cfg = config.load()
        self.assertEqual((cfg["engine"], cfg["claude_config_dir"], cfg["scan_roots"]),
                         ("claude", "", [str(self.home / "code")]))
        self.assertEqual(cfg["env_path"], os.environ["PATH"])
        self.assertTrue((self.home / "token").exists())
        self.assertTrue((self.home / "auto" / "ugetme.service").exists())
        settings = self.handy_settings()
        self.assertEqual(settings["post_process_selected_prompt_id"], "ugetme")
        self.assertEqual(settings["bindings"]["transcribe"]["current_binding"], "b")
        self.assertEqual(vocab.load(self.home / "vocab.md").projects, ["nimbus-api"])

    def test_setup_prints_the_plugin_commands(self):
        out = self.run_setup(["--yes"] + OPENAI + SKIP)[1]
        self.assertIn("/plugin marketplace add hassan-mir/ugetme", out)
        self.assertIn("/plugin install ugetme@ugetme", out)

    def test_openai_engine_flags(self):
        self.run_setup(["--yes", "--engine", "openai", "--openai-url", "http://localhost:11434/v1", "--openai-model",
                        "llama3"] + SKIP)
        cfg = config.load()
        self.assertEqual((cfg["engine"], cfg["openai"]["base_url"], cfg["openai"]["model"]),
                         ("openai", "http://localhost:11434/v1", "llama3"))

    def test_a_damaged_handy_file_gives_a_message_not_a_traceback(self):
        for text in ("{not json", "[]", '{"settings": {"post_process_providers": 3}}'):
            self.handy_file.write_text(text)
            self.assertIn("could not read Handy's settings", wizard.setup_handy(7337, "tok", True, False, False), text)
        code, out = run_cli("handy", "setup", "--no-auto-submit")
        self.assertIn("could not read Handy's settings", out)

    def test_handy_running_is_not_changed(self):
        os.environ["UGETME_HANDY_RUNNING"] = "1"
        out = self.run_setup(["--yes", "--no-scan", "--no-autostart", "--handy", "--no-test"])[1]
        self.assertIn("Handy is running, so its settings were not changed", out)
        settings = self.handy_settings()
        self.assertNotIn("post_process_selected_prompt_id", settings)

    def test_list_logins(self):
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "settings.json").write_text("{}")
        with mock.patch.object(wizard.Path, "home", return_value=self.home):
            code, out = run_cli("setup", "--list-logins")
        self.assertEqual(json.loads(out), [str(self.home / ".claude")])

    def test_login_flag_for_the_default_login_is_stored_as_default(self):
        (self.home / ".claude").mkdir()
        with mock.patch.object(wizard.Path, "home", return_value=self.home):
            self.run_setup(["--yes", "--engine", "claude", "--login", str(self.home / ".claude")] + SKIP)
        self.assertEqual(config.load()["claude_config_dir"], "")

    def test_a_single_non_default_login_is_used(self):
        other = self.home / ".claude-work"
        other.mkdir()
        (other / "settings.json").write_text("{}")
        with mock.patch.object(wizard.Path, "home", return_value=self.home):
            self.run_setup(["--yes", "--engine", "claude"] + SKIP)
        self.assertEqual(config.load()["claude_config_dir"], str(other))

    def test_relative_paths_are_saved_in_full(self):
        (self.home / "code").mkdir()
        cwd = os.getcwd()
        os.chdir(self.home)
        self.addCleanup(os.chdir, cwd)
        self.run_setup(["--yes", "--engine", "claude", "--login", "some-login", "--scan-root", "code",
                        "--no-autostart", "--no-handy", "--no-test"])
        cfg = config.load()
        self.assertEqual((cfg["claude_config_dir"], cfg["scan_roots"]),
                         (str(self.home / "some-login"), [str(self.home / "code")]))

    def test_trust_and_untrust(self):
        work = self.home / ".claude-work"
        code, out = run_cli("trust", str(work))
        self.assertEqual(code, 0)
        self.assertEqual(config.load()["trusted_logins"], [str(work)])
        run_cli("trust", str(work))
        self.assertEqual(config.load()["trusted_logins"], [str(work)])
        code, out = run_cli("trust")
        self.assertIn(str(work), out)
        self.assertEqual(run_cli("untrust", str(work))[0], 0)
        self.assertEqual(config.load()["trusted_logins"], [])
        self.assertEqual(run_cli("untrust", str(work))[0], 1)

    def test_setup_can_trust_the_other_logins(self):
        for folder in (".claude", ".claude-work"):
            (self.home / folder).mkdir()
            (self.home / folder / "settings.json").write_text("{}")
        base = ["--yes", "--engine", "claude", "--login", str(self.home / ".claude")] + SKIP
        with mock.patch.object(wizard.Path, "home", return_value=self.home):
            self.run_setup(base)
            self.assertEqual(config.load()["trusted_logins"], [])
            self.run_setup(base + ["--trust-other-logins"])
        self.assertEqual(config.load()["trusted_logins"], [str(self.home / ".claude-work")])

    def test_trust_compares_normal_forms_and_refuses_the_engine_login(self):
        work = self.home / ".claude-work"
        work.mkdir()
        self.set_config(trusted_logins=[str(work) + "/"], claude_config_dir=str(self.home / ".claude-main"))
        run_cli("trust", str(work))
        self.assertEqual(len(config.load()["trusted_logins"]), 1)
        self.assertEqual(run_cli("untrust", str(work))[0], 0)
        self.assertEqual(config.load()["trusted_logins"], [])
        code, out = run_cli("trust", str(self.home / ".claude-main"))
        self.assertEqual(code, 1)
        self.assertEqual(config.load()["trusted_logins"], [])
        code, out = run_cli("trust", str(self.home / "missing"))
        self.assertIn("does not exist", out)

    def test_setup_clears_trusted_logins_when_the_answer_is_no(self):
        for folder in (".claude", ".claude-work"):
            (self.home / folder).mkdir()
            (self.home / folder / "settings.json").write_text("{}")
        base = ["--yes", "--engine", "claude"] + SKIP
        with mock.patch.object(wizard.Path, "home", return_value=self.home):
            self.run_setup(base + ["--login", str(self.home / ".claude"), "--trust-other-logins"])
            self.run_setup(base + ["--login", str(self.home / ".claude-work"), "--no-trust-other-logins"])
        self.assertEqual(config.load()["trusted_logins"], [])

    def test_setup_again_without_a_trust_answer_keeps_the_trusted_logins(self):
        for folder in (".claude", ".claude-work"):
            (self.home / folder).mkdir()
            (self.home / folder / "settings.json").write_text("{}")
        base = ["--yes", "--engine", "claude"] + SKIP
        work = str(self.home / ".claude-work")
        with mock.patch.object(wizard.Path, "home", return_value=self.home):
            self.run_setup(base + ["--login", str(self.home / ".claude"), "--trust-other-logins"])
            self.run_setup(base + ["--login", str(self.home / ".claude")])
            self.assertEqual(config.load()["trusted_logins"], [work])
            self.run_setup(base + ["--login", work])   # the login that cleans cannot be trusted
        self.assertEqual(config.load()["trusted_logins"], [])

    def test_setup_reports_a_failed_test_as_a_failure(self):
        failed = {"clean": wizard.SAMPLE, "failed": "cannot reach http://h/v1. Is your model server running?"}
        with mock.patch.object(wizard.client, "ensure_running", return_value=True), \
                mock.patch.object(wizard.client, "request", return_value=failed):
            code, out = self.run_setup(["--yes"] + OPENAI + ["--no-scan", "--no-autostart", "--no-handy"])
        self.assertEqual(code, 1)
        self.assertIn("✗ Test failed: cannot reach http://h/v1", out)

    def test_setup_without_a_terminal_says_it_uses_the_defaults(self):
        out = self.run_setup(OPENAI + SKIP)[1]
        self.assertIn("No terminal, so setup uses the defaults", out)

    def test_setup_continues_when_autostart_fails(self):
        with mock.patch.object(wizard.autostart, "install", side_effect=FileNotFoundError("cmd.exe")):
            code, out = self.run_setup(["--yes"] + OPENAI + ["--no-scan", "--autostart", "--handy", "--no-test"])
        self.assertEqual(code, 0)
        self.assertIn("✗ Autostart failed: cmd.exe", out)
        self.assertIn("✓ Handy is set up", out)

    def test_autostart_command_reports_a_failure(self):
        with mock.patch.object(cli.autostart, "install", side_effect=OSError("no startup folder")):
            code, out = run_cli("autostart", "on")
        self.assertEqual(code, 1)
        self.assertIn("Autostart failed: no startup folder", out)

    def test_setup_says_how_to_get_handy_when_it_is_missing(self):
        self.handy_file.unlink()
        out = self.run_setup(["--yes"] + OPENAI + ["--no-scan", "--no-autostart", "--no-test"])[1]
        self.assertIn("Handy not found", out)
        self.assertIn("ugetme handy setup", out)
        self.assertNotIn("Handy", self.run_setup(["--yes"] + OPENAI + SKIP)[1])

    def test_setup_says_when_claude_is_missing(self):
        with mock.patch.object(wizard.shutil, "which", return_value=None):
            out = self.run_setup(["--yes", "--openai-url", "http://h/v1", "--openai-model", "m"] + SKIP)[1]
        self.assertEqual(config.load()["engine"], "openai")
        self.assertIn("Claude Code (claude) was not found", out)
        self.assertIn("✓ Engine: http://h/v1", out)

    def bindings(self):
        b = self.handy_settings()["bindings"]
        return b["transcribe"]["current_binding"], b["transcribe_with_post_process"]["current_binding"]

    def test_setup_check_mode_keeps_the_main_handy_hotkey_raw(self):
        self.run_setup(HANDY_ONLY + ["--mode", "check"])
        self.assertEqual(config.load()["mode"], "check")
        self.assertEqual(self.bindings(), ("a", "b"))

    def test_mode_command_moves_the_handy_hotkey(self):
        self.run_setup(HANDY_ONLY)
        self.assertEqual(self.bindings(), ("b", "a"))  # auto: the main key cleans
        code, out = run_cli("mode", "check")
        self.assertEqual(code, 0)
        self.assertEqual((config.load()["mode"], self.bindings()), ("check", ("a", "b")))
        self.assertIn("every prompt", out)
        run_cli("config", "mode", "auto")
        self.assertEqual((config.load()["mode"], self.bindings()), ("auto", ("b", "a")))
        code, out = run_cli("mode")
        self.assertIn("auto (now)", out)
        self.assertIn("manual", out)
        self.assertEqual(run_cli("mode", "sometimes")[0], 1)

    def test_mode_with_handy_running_says_to_quit_it(self):
        self.run_setup(HANDY_ONLY)
        os.environ["UGETME_HANDY_RUNNING"] = "1"
        code, out = run_cli("mode", "manual")
        self.assertEqual(config.load()["mode"], "manual")
        self.assertEqual(self.bindings(), ("b", "a"))
        self.assertIn("ugetme handy setup", out)

    def test_status_shows_the_mode(self):
        self.set_config(mode="check")
        self.assertIn("mode: check", run_cli("status")[1])

    def test_scan_count_is_singular_for_one(self):
        (self.home / "code" / "nimbus-api").mkdir(parents=True)
        out = run_cli("scan", str(self.home / "code"))[1]
        self.assertIn("ugetme found 1 project name", out)
        self.assertNotIn("names", out)

    def test_detect_logins(self):
        for folder, marker in ((".claude", "settings.json"), (".claude-second", ".credentials.json")):
            (self.home / folder).mkdir()
            (self.home / folder / marker).write_text("{}")
        (self.home / ".claude-empty").mkdir()
        with mock.patch.object(wizard.Path, "home", return_value=self.home):
            self.assertEqual(wizard.detect_logins(), [str(self.home / ".claude"), str(self.home / ".claude-second")])

    def test_no_words_come_from_outside_the_ugetme_home(self):
        old = self.home / ".claude" / "getme"
        old.mkdir(parents=True)
        (old / "vocab.md").write_text('# Terms\n- Nimbus (heard: "nimbis")\n')
        with mock.patch.object(wizard.Path, "home", return_value=self.home):
            self.run_setup(["--yes"] + SKIP)
        self.assertEqual(vocab.load(self.home / "vocab.md").terms, [])
