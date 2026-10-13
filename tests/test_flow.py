"""Offline tests: config merge, selectors override, chrome discovery, captions/finish with real ffmpeg.

Run: python -m unittest discover -s tests -v   (needs ffmpeg + pillow; no browser, no network)
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load_flow(home):
    os.environ["FLOW_DIRECTOR_HOME"] = str(home)
    import flow
    return importlib.reload(flow)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.flow = load_flow(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_then_partial_override_merges_nested(self):
        Path(self.tmp.name, "config.json").write_text(json.dumps({"format": {"width": 720}, "mode": "auto"}))
        cfg = self.flow.load_config()
        self.assertEqual(cfg["format"], {"width": 720, "height": 1920, "duration": 10})
        self.assertEqual(cfg["mode"], "auto")
        self.assertTrue(cfg["captions"]["enabled"])

    def test_setup_saves_and_reports_next_steps(self):
        parser = self.flow.build_parser()
        args = parser.parse_args(["setup", "--no-browser", "--characters", "Mia, Leo", "--width", "720",
                                  "--height", "1280", "--captions", "off", "--mode", "auto", "--port", "9777"])
        result = self.flow.cmd_setup(args, self.flow.load_config())
        saved = json.loads(Path(self.tmp.name, "config.json").read_text())
        self.assertEqual(saved["characters"], ["Mia", "Leo"])
        self.assertEqual((saved["format"]["width"], saved["format"]["height"]), (720, 1280))
        self.assertFalse(saved["captions"]["enabled"])
        self.assertEqual(saved["port"], 9777)
        self.assertEqual(result["login"], "no_browser")
        self.assertTrue(any("sign in" in s.lower() for s in result["next"]))
        self.assertTrue(any("project" in s.lower() for s in result["next"]))

    def test_selector_override_wins(self):
        Path(self.tmp.name, "selectors.json").write_text(json.dumps({"composer": "#mine", "stop_patterns": {"policy": "xyz"}}))
        sel = self.flow.selectors()
        self.assertEqual(sel["composer"], "#mine")
        self.assertEqual(sel["stop_patterns"]["policy"], "xyz")
        self.assertIn("challenge", sel["stop_patterns"])  # untouched keys survive
        self.assertEqual(sel["send_button"], json.loads((ROOT / "selectors.json").read_text())["send_button"])

    def test_project_id_extraction(self):
        pid = "12345678-1234-1234-1234-123456789abc"
        self.assertEqual(self.flow._project_id(f"https://flow.google.com/u/0/project/{pid}"), pid)
        self.assertIsNone(self.flow._project_id("https://flow.google.com/"))

    def test_credits_tracking(self):
        parser = self.flow.build_parser()
        cfg = self.flow.load_config()
        self.flow.cmd_credits(parser.parse_args(["credits", "--add", "4"]), cfg)
        out = self.flow.cmd_credits(parser.parse_args(["credits", "--add", "3"]), cfg)
        self.assertEqual((out["used"], out["remaining"]), (7, cfg["max_credits"] - 7))
        self.assertEqual(self.flow.cmd_credits(parser.parse_args(["credits", "--reset"]), cfg)["used"], 0)


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.flow = load_flow(self.tmp.name)
        self.sel = self.flow.selectors()

    def tearDown(self):
        self.tmp.cleanup()

    def snap(self, **kw):
        base = dict(url="https://flow.google.com/u/0/project/x", dialog="", alerts="", permission="",
                    agent_panel=True, composer=True)
        return {**base, **kw}

    def test_states(self):
        c = self.flow.classify
        self.assertEqual(c(self.snap(), self.sel), "ready")
        self.assertEqual(c(self.snap(url="https://accounts.google.com/signin"), self.sel), "signed_out")
        self.assertEqual(c(self.snap(alerts="Unusual traffic detected"), self.sel), "challenge")
        self.assertEqual(c(self.snap(dialog="You are out of credits"), self.sel), "credits")
        self.assertEqual(c(self.snap(permission="Generate 8s video for 20 credits"), self.sel), "permission_card")
        self.assertEqual(c(self.snap(agent_panel=False), self.sel), "unknown")


class PermissionAndNameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.flow = load_flow(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_permission_card(self):
        text = ("I am going to generate one 10-second vertical video clip starring Mr. bear using Omni 1.1 Flash. "
                "Would you like me to kick off this 1 video generation, costing 15 credits?")
        info = self.flow.parse_permission(text)
        self.assertEqual((info["cost"], info["model"], info["seconds"]), (15, "Omni 1.1 Flash", 10))
        self.assertEqual(self.flow.parse_permission("nothing here"), {"cost": None, "model": None, "seconds": None})

    def test_card_is_cleared_after_it_is_handled(self):
        raw = {"permission_text": "costing 15 credits", "permission_count": 1,
               "permission_buttons": [{"text": "Approve", "aria": None, "disabled": False}]}
        first = self.flow.apply_permission_state(raw, {})
        self.assertEqual(first["permission_buttons"], ["Approve"])
        self.flow.mark_card_handled(first["_card_sig"])
        again = self.flow.apply_permission_state(raw, self.flow.load_state())
        self.assertEqual(again["permission"], "")
        self.assertTrue(again["permission_resolved"])
        newer = self.flow.apply_permission_state({**raw, "permission_count": 2}, self.flow.load_state())
        self.assertTrue(newer["permission"])  # a new card with the same text is pending again

    def test_read_only_radio_card_is_resolved(self):
        raw = {"permission_text": "costing 15 credits", "permission_count": 1,
               "permission_buttons": [{"text": "Approve", "disabled": True, "checked": True},
                                      {"text": "Reject", "disabled": True, "checked": False}]}
        card = self.flow.apply_permission_state(raw, {})
        self.assertEqual(card["permission"], "")
        self.assertTrue(card["permission_resolved"])

    def test_server_display_env(self):
        Path(self.tmp.name, "display.env").write_text("DISPLAY=:987\n")
        self.assertIsNone(self.flow.server_display())          # no such X socket -> ignored
        with mock.patch.object(self.flow.Path, "exists", return_value=True):
            self.assertEqual(self.flow.server_display(), ":987")

    def test_character_matching(self):
        m = self.flow.match_name
        self.assertEqual(m("mr bear", ["Mr. bear", "Mia"]), ("Mr. bear", "normalized"))
        self.assertEqual(m("Mr. bear", ["Mr. bear"]), ("Mr. bear", "exact"))
        self.assertEqual(m("Mister bear", ["Mr. bear", "Mia"])[0], "Mr. bear")
        with self.assertRaises(self.flow.FlowError) as ctx:
            m("zzz", ["Mr. bear", "Mia"])
        self.assertIn("Mia", ctx.exception.hint)

    def test_read_text_arg_strips_powershell_bom(self):
        path = Path(self.tmp.name, "msg.txt")
        path.write_bytes(b"\xef\xbb\xbfhello \xc3\xa9")
        self.assertEqual(self.flow.read_text_arg(str(path)), "hello é")

    def test_repair_install_copies_only_missing_files(self):
        src = Path(self.tmp.name, "repo")
        (src / "x").mkdir(parents=True)
        import zipfile
        archive = Path(self.tmp.name, "repo.zip")
        with zipfile.ZipFile(archive, "w") as z:
            for rel in self.flow.REQUIRED_FILES:
                z.writestr("skill-main/" + rel, "from zip")
        fake_root = Path(self.tmp.name, "installed")
        (fake_root / "scripts").mkdir(parents=True)
        (fake_root / "SKILL.md").write_text("keep me")
        with mock.patch.object(self.flow, "SKILL_DIR", fake_root), \
                mock.patch.dict(os.environ, {"FLOW_REPAIR_URL": archive.as_uri()}):
            result = self.flow.repair_install()
        self.assertEqual(result["still_missing"], [])
        self.assertEqual((fake_root / "SKILL.md").read_text(), "keep me")
        self.assertEqual((fake_root / "scripts" / "captions.py").read_text(), "from zip")


class BrowserDiscoveryTests(unittest.TestCase):
    def test_explicit_chrome_path_is_used_when_it_exists(self):
        tmp = tempfile.TemporaryDirectory()
        flow = load_flow(tmp.name)
        fake = Path(tmp.name, "chrome-fake")
        fake.write_text("x")
        self.assertEqual(flow.find_chrome(str(fake)), str(fake))
        tmp.cleanup()

    def test_which_fallback(self):
        tmp = tempfile.TemporaryDirectory()
        flow = load_flow(tmp.name)
        with mock.patch.object(flow.shutil, "which", side_effect=lambda n: "/x/chromium" if n == "chromium" else None), \
                mock.patch.object(flow.os, "name", "posix"), mock.patch.object(flow.sys, "platform", "linux"):
            self.assertEqual(flow.find_chrome(None), "/x/chromium")
        tmp.cleanup()

    def test_missing_browser_gives_actionable_error(self):
        tmp = tempfile.TemporaryDirectory()
        flow = load_flow(tmp.name)
        cfg = flow.load_config()
        with mock.patch.object(flow, "cdp_alive", return_value=False), mock.patch.object(flow, "find_chrome", return_value=None):
            with self.assertRaises(flow.FlowError) as ctx:
                flow.browser_start(cfg)
        self.assertIn("bootstrap", ctx.exception.hint)
        tmp.cleanup()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class CaptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clip = Path(cls.tmp.name, "clip.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=24",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", str(cls.clip)], check=True)
        import captions
        cls.captions = captions

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_scale_pad_without_caption(self):
        out = self.captions.finish(self.clip, Path(self.tmp.name, "plain.mp4"), 720, 1280)
        self.assertEqual((out["width"], out["height"]), (720, 1280))
        self.assertTrue(out["has_audio"])
        self.assertAlmostEqual(out["duration"], 2.0, delta=0.2)

    def test_caption_with_hostile_text_does_not_break_ffmpeg(self):
        text = "It's 5:00 'quoted' \"double\" %{expr} \\ , ; [x] émoji 🎬"
        out = self.captions.finish(self.clip, Path(self.tmp.name, "cap.mp4"), 720, 1280, caption=text,
                                   layout={"y": 0.2, "start": 0.2})
        self.assertEqual((out["width"], out["height"]), (720, 1280))
        self.assertIsNotNone(out["caption"])

    def test_long_caption_shrinks_to_fit_and_stays_in_frame(self):
        info = self.captions.render_overlay("word " * 40, 720, 1280, {"max_lines": 3}, self.captions.find_font(),
                                            Path(self.tmp.name, "o.png"))
        self.assertLessEqual(info["lines"], 3)
        left, top, right, bottom = info["bounds"]
        self.assertTrue(0 <= left and right <= 720 and 0 <= top and bottom <= 1280)

    def test_trim(self):
        out = self.captions.finish(self.clip, Path(self.tmp.name, "trim.mp4"), 360, 640, trim=1)
        self.assertAlmostEqual(out["duration"], 1.0, delta=0.2)

    def test_auto_y_and_strip_audio(self):
        out = self.captions.finish(self.clip, Path(self.tmp.name, "auto.mp4"), 720, 1280, caption="Hello there",
                                   layout={"y": "auto"}, strip_audio=True)
        self.assertFalse(out["has_audio"])
        self.assertTrue(out["audio_stripped"])
        self.assertTrue(0.08 <= out["caption"]["y"] <= 0.7)
        self.assertIn("y_auto", out["caption"])

    def test_missing_input_is_clear(self):
        with self.assertRaises(FileNotFoundError):
            self.captions.finish(Path(self.tmp.name, "nope.mp4"), Path(self.tmp.name, "o.mp4"), 100, 100)


class CliContractTests(unittest.TestCase):
    def test_errors_are_json_with_hint_and_exit_2(self):
        with tempfile.TemporaryDirectory() as home:
            import socket
            with socket.socket() as sock:           # a port nothing listens on, so a real Flow browser cannot interfere
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            Path(home, "config.json").write_text(json.dumps({"port": port}))
            env = dict(os.environ, FLOW_DIRECTOR_HOME=home, FLOW_NO_REEXEC="1")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "flow.py"), "snapshot"],
                                  capture_output=True, text=True, env=env)
        payload = json.loads(done.stdout)
        self.assertEqual(done.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["hint"])

    def test_help_lists_all_commands(self):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "flow.py"), "--help"], capture_output=True, text=True,
                              env=dict(os.environ, FLOW_NO_REEXEC="1"))
        for command in ("setup", "doctor", "browser", "send", "attach", "wait", "download", "captions", "inspect", "eval"):
            self.assertIn(command, done.stdout)


if __name__ == "__main__":
    unittest.main()
