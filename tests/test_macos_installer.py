"""Exercise the native installer only against isolated temporary card directories."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
OWNER = b"Nextbase622GW Bluetooth Recovery Kit 0.2.0\n"
PAYLOAD = {
    "autoexec.ash": b"sleep 20000\nt app linux_cmd /bin/sh /tmp/SD0/nb-bt-recover.sh\n",
    "nb-bt-recover.sh": b"#!/bin/sh\nprintf 'temporary fixture only\\n'\n",
    "usb.console": b"PortableMultimediaLtdt/aNextbase",
}


class MacOSInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nb-installer-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.kit = self.root / "kit with spaces"
        (self.kit / "payload").mkdir(parents=True)
        for name, data in PAYLOAD.items():
            (self.kit / "payload" / name).write_bytes(data)
        (self.kit / "SHA256SUMS").write_text(
            "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n"
                    for name, data in PAYLOAD.items()), encoding="ascii"
        )
        self.card = self.make_card("card with spaces")

    def make_card(self, name, identity=None):
        card = self.root / name
        card.mkdir()
        (card / "Nextbase.info").write_bytes(
            identity if identity is not None else
            b"NBDVR622GWA-R13.3\r\nModel: 622GW\r\nFirmware: R13.3\r\n"
        )
        (card / "DCIM").mkdir()
        (card / "DCIM" / "video.mp4").write_bytes(b"preserve video")
        return card

    def run_installer(self, action="prepare", card=True, extra_env=None):
        source = PROJECT / "recovery-kit" / "prepare-macos.sh"
        self.assertTrue(source.is_file(), "native installer has not been implemented")
        target = self.kit / source.name
        shutil.copyfile(source, target)
        args = ["/bin/bash", str(target), action]
        if card:
            args.append(str(self.card if card is True else card))
        env = os.environ.copy()
        env["NB_RECOVERY_VOLUMES_ROOT"] = str(self.root / "discover")
        env.update(extra_env or {})
        return subprocess.run(args, capture_output=True, text=True, env=env, timeout=15)

    def snapshot(self):
        entries = {}
        for path in self.card.rglob("*"):
            rel = str(path.relative_to(self.card))
            if path.is_symlink():
                entries[rel] = ("symlink", os.readlink(path))
            elif path.is_file():
                entries[rel] = path.read_bytes()
            elif path.is_dir():
                entries[rel] = ("directory",)
        return entries

    def assert_refuses_unchanged(self, action="prepare", **kwargs):
        before = self.snapshot()
        result = self.run_installer(action, **kwargs)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)
        return result

    def prepare(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_prepare_copies_exact_payload_preserves_video_and_reports_eject(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name, data in PAYLOAD.items():
            self.assertEqual((self.card / name).read_bytes(), data)
        self.assertEqual((self.card / "nb-bt-recovery-kit.txt").read_bytes(), OWNER)
        self.assertEqual((self.card / "DCIM/video.mp4").read_bytes(), b"preserve video")
        self.assertIn("eject", result.stdout.lower())
        self.assertIn("pair", result.stdout.lower())
        self.assertFalse(list(self.card.glob(".nb-bt-recovery.stage.*")))

    def test_identity_refusals_do_not_mutate_card_or_echo_private_contents(self):
        for data in [b"", b"Model: 522GW\nFirmware: R13.3\n",
                     b"Model: 622GW\nFirmware: R12.0\n",
                     b"Model: 622GW\nModel: 622GW\nFirmware: R13.3\n",
                     b"Model: 622GW\nMODEL: 622GW\nFirmware: R13.3\n",
                     b"Model: 622GW\nFirmware: R13.3\nFirmware: R13.3\n",
                     b"Model: 622GW\nFirmware: R13.3\nFIRMWARE: R13.3\n",
                     b"Model: 622GW extra\nFirmware: R13.3\n"]:
            with self.subTest(identity=data):
                (self.card / "Nextbase.info").write_bytes(data + b"Serial No: PRIVATE-SENTINEL\n")
                result = self.assert_refuses_unchanged()
                self.assertNotIn("PRIVATE-SENTINEL", result.stdout + result.stderr)
        (self.card / "Nextbase.info").unlink()
        self.assert_refuses_unchanged()

    def test_existing_hooks_firmware_and_legacy_diagnostics_are_preserved(self):
        for name in ["autoexec.ash", "AUTOEXEC.ASH", "usb.console", "usb.multi.console",
                     "usb.unknown.console", "nb-bt-recover.sh", "nb-bt-recovery-kit.txt",
                     "FW622GWA.bin", "ld622gwa.BIN", "bt-diagnostics.sh",
                     "bt-late-diagnostics.sh", "bt-start-test.sh", "bt-storage-diagnostics.sh"]:
            with self.subTest(name=name):
                collision = self.card / name
                collision.write_bytes(b"user-owned bytes")
                self.assert_refuses_unchanged()
                collision.unlink()

    def test_existing_runtime_guard_is_preserved_even_if_owned(self):
        guard = self.card / "nb-bt-recovery.claimed"
        guard.mkdir()
        (guard / "owner.txt").write_bytes(OWNER)
        self.assert_refuses_unchanged()

    def test_corrupted_missing_duplicate_or_unexpected_manifest_payload_refuses(self):
        payload = self.kit / "payload/nb-bt-recover.sh"
        payload.write_bytes(b"corrupted")
        self.assert_refuses_unchanged()
        payload.write_bytes(PAYLOAD[payload.name])
        manifest = self.kit / "SHA256SUMS"
        original = manifest.read_bytes()
        for bad in [original.splitlines(keepends=True)[0], original + original.splitlines(keepends=True)[0],
                    original + b"0" * 64 + b"  ../unexpected\n", b"bad manifest\n"]:
            manifest.write_bytes(bad)
            self.assert_refuses_unchanged()
        manifest.write_bytes(original)
        payload.unlink()
        self.assert_refuses_unchanged()

    def test_symlinks_on_identity_payload_and_managed_paths_are_refused(self):
        target = self.root / "unknown"
        target.write_bytes(b"unknown")
        for name in ["autoexec.ash", "nb-bt-recover.sh", "usb.console", "nb-bt-recovery-kit.txt",
                     "nb-bt-recovery.claimed"]:
            with self.subTest(name=name):
                link = self.card / name
                link.symlink_to(target)
                self.assert_refuses_unchanged()
                link.unlink()
        info = self.card / "Nextbase.info"
        identity = info.read_bytes()
        info.unlink()
        target.write_bytes(identity)
        info.symlink_to(target)
        self.assert_refuses_unchanged()
        info.unlink()
        info.write_bytes(identity)
        payload = self.kit / "payload/usb.console"
        payload.unlink()
        payload.symlink_to(target)
        self.assert_refuses_unchanged()

    def test_volume_symlink_is_refused_including_trailing_slash(self):
        alias = self.root / "alias"
        alias.symlink_to(self.card, target_is_directory=True)
        self.assert_refuses_unchanged(card=str(alias) + "/")

    def test_status_is_read_only_for_prepared_and_unprepared_cards(self):
        before = self.snapshot()
        result = self.run_installer("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not prepared", result.stdout.lower())
        self.assertEqual(before, self.snapshot())
        self.prepare()
        before = self.snapshot()
        result = self.run_installer("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("prepared", result.stdout.lower())
        self.assertEqual(before, self.snapshot())

    def test_remove_preserves_results_videos_and_unknown_files_and_consumed_token(self):
        self.prepare()
        resultdir = self.card / "nb-bt-recovery-1"
        resultdir.mkdir()
        (resultdir / "private.log").write_bytes(b"keep results")
        (self.card / "notes.txt").write_bytes(b"keep notes")
        (self.card / "usb.console").rename(resultdir / "usb.console.used")
        guard = self.card / "nb-bt-recovery.claimed"
        guard.mkdir()
        (guard / "owner.txt").write_bytes(OWNER)
        result = self.run_installer("remove")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in [*PAYLOAD, "nb-bt-recovery-kit.txt", "nb-bt-recovery.claimed"]:
            self.assertFalse((self.card / name).exists(), name)
        self.assertEqual((self.card / "DCIM/video.mp4").read_bytes(), b"preserve video")
        self.assertEqual((self.card / "notes.txt").read_bytes(), b"keep notes")
        self.assertEqual((resultdir / "private.log").read_bytes(), b"keep results")
        self.assertEqual((resultdir / "usb.console.used").read_bytes(), PAYLOAD["usb.console"])

    def test_remove_refuses_modified_payload_marker_or_guard_without_changes(self):
        self.prepare()
        for name in [*PAYLOAD, "nb-bt-recovery-kit.txt"]:
            path = self.card / name
            original = path.read_bytes()
            path.write_bytes(b"changed")
            self.assert_refuses_unchanged("remove")
            path.write_bytes(original)
        guard = self.card / "nb-bt-recovery.claimed"
        guard.mkdir()
        owner = guard / "owner.txt"
        owner.write_bytes(b"different owner\n")
        self.assert_refuses_unchanged("remove")
        owner.write_bytes(OWNER)
        (guard / "unknown.txt").write_bytes(b"keep me")
        self.assert_refuses_unchanged("remove")

    def test_reprepare_refuses_and_remove_then_prepare_rearms(self):
        self.prepare()
        self.assert_refuses_unchanged()
        result = self.run_installer("remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.prepare()

    def test_stage_copy_and_final_rename_failure_leave_no_boot_hook(self):
        for command in ["cp", "mv"]:
            with self.subTest(command=command):
                bindir = self.root / ("fail-" + command)
                bindir.mkdir()
                wrapper = bindir / command
                if command == "cp":
                    script = '#!/bin/bash\ncase "$1" in */usb.console) exit 77;; esac\nexec /bin/cp "$@"\n'
                else:
                    script = '#!/bin/bash\nfor arg in "$@"; do case "$arg" in */autoexec.ash) exit 77;; esac; done\nexec /bin/mv "$@"\n'
                wrapper.write_text(script)
                wrapper.chmod(0o755)
                self.assert_refuses_unchanged(extra_env={"PATH": str(bindir) + os.pathsep + os.environ["PATH"]})
                self.assertFalse((self.card / "autoexec.ash").exists())

    def test_failure_or_signal_after_hook_rename_rolls_back_all_owned_files(self):
        for outcome in ["exit 77", 'kill -TERM "$PPID"; exit 0']:
            with self.subTest(outcome=outcome):
                bindir = self.root / ("interrupt-" + str(len(outcome)))
                bindir.mkdir()
                wrapper = bindir / "mv"
                wrapper.write_text(
                    '#!/bin/bash\n/bin/mv "$@" || exit $?\n'
                    'for arg in "$@"; do case "$arg" in */autoexec.ash) '
                    + outcome + ';; esac; done\n'
                )
                wrapper.chmod(0o755)
                self.assert_refuses_unchanged(extra_env={"PATH": str(bindir) + os.pathsep + os.environ["PATH"]})

    def test_guard_owner_symlink_blocks_removal(self):
        self.prepare()
        guard = self.card / "nb-bt-recovery.claimed"
        guard.mkdir()
        owner = self.root / "external-owner"
        owner.write_bytes(OWNER)
        (guard / "owner.txt").symlink_to(owner)
        self.assert_refuses_unchanged("remove")
        self.assertEqual(owner.read_bytes(), OWNER)

    def test_finder_launcher_works_with_spaces_without_interactive_stdin(self):
        source = PROJECT / "recovery-kit"
        self.assertTrue((source / "Recover Bluetooth.command").is_file())
        for name in ["prepare-macos.sh", "Recover Bluetooth.command"]:
            shutil.copyfile(source / name, self.kit / name)
        result = subprocess.run(
            ["/bin/bash", str(self.kit / "Recover Bluetooth.command"), str(self.card)],
            input="", capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.card / "autoexec.ash").read_bytes(), PAYLOAD["autoexec.ash"])

    def test_autodetection_requires_exactly_one_compatible_card(self):
        discovery = self.root / "discover"
        discovery.mkdir()
        self.assertNotEqual(self.run_installer(card=False).returncode, 0)
        first = discovery / "first"
        self.card.rename(first)
        self.card = first
        result = self.run_installer("status", card=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        second = discovery / "second"
        shutil.copytree(first, second)
        self.assert_refuses_unchanged(card=False)
        self.assertFalse((second / "autoexec.ash").exists())


if __name__ == "__main__":
    unittest.main()
