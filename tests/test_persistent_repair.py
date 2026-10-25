"""Host-only safety checks; never mount, format, or open a physical camera."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import test_persistent_results as result_fixtures

if os.name == "posix":
    import pty
    import select


ROOT = Path(__file__).resolve().parents[1]


def load_wizard():
    directory = ROOT / "persistent-repair"
    sys.path.insert(0, str(directory))
    try:
        spec = importlib.util.spec_from_file_location("persistent_wizard", directory / "repair.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class SyntheticHost:
    """Simulate physical boots using public, invented result fixtures only."""
    def __init__(self, card, mutate=None):
        self.card, self.mutate = card, mutate
        self.boots, self.ejections, self.checks = [], 0, 0

    def info(self, card):
        if card != self.card:
            raise AssertionError("wrong card")

    def verify(self, card):
        self.info(card)
        self.checks += 1
        return b"synthetic readonly SD check passed\n"

    def eject(self, card):
        self.info(card)
        self.ejections += 1

    def capture(self, tool, output, phase):
        self.boots.append(phase)
        factory = result_fixtures.PersistentResultTests()
        factory.hook = (self.card / "autoexec.ash").read_bytes()
        factory.script = (self.card / "nb-a-preflight.sh").read_bytes() if phase == "backup" else b"unused"
        factory.identity = (self.card / "Nextbase.info").read_bytes()
        if phase == "backup":
            factory.folder = self.card / "nb-a-preflight"; factory.folder.mkdir()
            factory.preflight()
            factory.folder = self.card / "bt-nand-backup-1"; factory.folder.mkdir()
            factory.backup()
            claim = self.card / "bt-nand-backup.claimed"; claim.mkdir()
            (claim / "output.txt").write_text("/tmp/SD0/bt-nand-backup-1\n")
            (self.card / "usb.console").unlink()
            data = b"NAND capture wrapper ended; inspect SD result files.\n"
        elif phase == "dryrun":
            (self.card / "NBFA01.claimed").mkdir()
            data = b"NBFA01_DRYRUN\n"
        elif phase == "rehearsal_skip":
            data = b"NBFA01_SKIP\n"
        elif phase == "format":
            (self.card / "NBFA02.claimed").mkdir()
            data = b"NBFA02_BEGIN\nDrive 'A' format done.\n"
        elif phase == "stock":
            data = b"AMSG_EVENT_BT_BOOTED\nNBFA02_SKIP\n"
        elif phase == "observer":
            factory.folder = self.card / "bt-persistence-capture-1"; factory.folder.mkdir()
            factory.persistence()
            shutil.move(self.card / "usb.console", factory.folder / "usb.console.used")
            claim = self.card / "bt-persistence-capture.claimed"; claim.mkdir()
            (claim / "output.txt").write_text("/tmp/SD0/bt-persistence-capture-1\n")
            data = b"Persistence observer ended; inspect SD results.\n"
        else:
            raise AssertionError("unexpected boot")
        if self.mutate:
            replacement = self.mutate(self, phase)
            if replacement is not None:
                data = replacement
        output.mkdir()
        (output / "serial-rx.bin").write_bytes(data)
        return data


class PersistentHostTests(unittest.TestCase):
    def setUp(self):
        self.w = load_wizard()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.card = self.base / "card with spaces"
        self.card.mkdir()
        (self.card / "Nextbase.info").write_bytes(b"Model: 622GW\r\nFirmware: R13.3\r\n")
        (self.card / "video.mp4").write_bytes(b"do not copy or erase")
        self.identity = self.w.verify_identity(self.card)
        self.assets = {"nb-a-preflight.sh": self.base / "script.sh", "autoexec.ash": self.base / "hook.ash"}
        self.assets["nb-a-preflight.sh"].write_bytes(b"fixture script\n")
        self.assets["autoexec.ash"].write_bytes(b"fixture hook\n")

    def journal(self):
        return self.w.Journal.create(self.base / "private", self.card, self.identity)

    def snapshot(self):
        return {str(p.relative_to(self.card)): p.read_bytes() for p in self.card.rglob("*") if p.is_file()}

    def test_unsupported_duplicate_and_linked_identity_refuse(self):
        for data in (b"Model: 522GW\nFirmware: R13.3\n", b"Model: 622GW\nModel: 622GW\nFirmware: R13.3\n", b"Model: 622GW\nFirmware: R13.2\n"):
            (self.card / "Nextbase.info").write_bytes(data)
            before = self.snapshot()
            with self.assertRaises(self.w.RepairError):
                self.w.verify_identity(self.card)
            self.assertEqual(before, self.snapshot())
        (self.card / "Nextbase.info").unlink()
        (self.card / "Nextbase.info").symlink_to(self.assets["nb-a-preflight.sh"])
        with self.assertRaises(self.w.RepairError):
            self.w.verify_identity(self.card)

    def test_changed_card_identity_cannot_be_adopted(self):
        (self.card / "Nextbase.info").write_bytes(b"Model: 622GW\nFirmware: R13.3\nSerial: another\n")
        with self.assertRaises(self.w.RepairError):
            self.w.verify_identity(self.card, self.identity)

    def test_new_session_refuses_existing_claim_hook_or_firmware(self):
        for name in ("NBFA02.claimed", "NBFA01.claimed", "autoexec.ash", "usb.multi.console", "FW622GWA.bin", "bt-nand-backup.claimed"):
            path = self.card / name
            path.write_bytes(b"unknown")
            before = self.snapshot()
            with self.assertRaises(self.w.RepairError):
                self.w.check_clean_card(self.card)
            self.assertEqual(before, self.snapshot())
            path.unlink()

    def test_stage_commits_hook_last_and_cleanup_preserves_data_claims_results(self):
        journal = self.journal()
        calls = []
        real_move = self.w.move_exclusive
        def move(source, destination):
            calls.append(destination.name)
            real_move(source, destination)
        with mock.patch.object(self.w, "move_exclusive", side_effect=move):
            self.w.stage_controls(self.card, journal, self.assets, "backup_staged")
        self.assertEqual(calls[-1], "autoexec.ash")
        (self.card / "NBFA02.claimed").mkdir()
        (self.card / "results").mkdir()
        (self.card / "results/keep.txt").write_bytes(b"private evidence")
        self.w.clear_controls(self.card, journal)
        self.assertTrue((self.card / "NBFA02.claimed").is_dir())
        self.assertEqual((self.card / "video.mp4").read_bytes(), b"do not copy or erase")
        self.assertEqual((self.card / "results/keep.txt").read_bytes(), b"private evidence")
        self.assertFalse((self.card / "autoexec.ash").exists())

    def test_partial_staging_failure_never_publishes_hook(self):
        journal = self.journal()
        def fail(source, destination):
            raise OSError("injected card failure")
        with mock.patch.object(self.w, "move_exclusive", side_effect=fail):
            with self.assertRaises((OSError, self.w.RepairError)):
                self.w.stage_controls(self.card, journal, self.assets, "backup_staged")
        self.assertFalse((self.card / "autoexec.ash").exists())
        self.w.clear_controls(self.card, journal)
        self.assertEqual((self.card / "video.mp4").read_bytes(), b"do not copy or erase")

    def test_modified_or_linked_controls_refuse_cleanup_without_deleting_other_files(self):
        journal = self.journal()
        self.w.stage_controls(self.card, journal, self.assets, "backup_staged")
        (self.card / "nb-a-preflight.sh").write_bytes(b"modified unknown bytes")
        before = self.snapshot()
        with self.assertRaises(self.w.RepairError):
            self.w.clear_controls(self.card, journal)
        self.assertEqual(before, self.snapshot())
        (self.card / "nb-a-preflight.sh").unlink()
        (self.card / "nb-a-preflight.sh").symlink_to(self.assets["nb-a-preflight.sh"])
        with self.assertRaises(self.w.RepairError):
            self.w.clear_controls(self.card, journal)

    def test_consent_is_typed_once_and_durable_before_any_format_hook(self):
        journal = self.journal()
        journal.data["phase"] = "rehearsed"
        journal.save()
        before = self.snapshot()
        for text in ("", "yes", "format drive a once"):
            with self.assertRaises(self.w.RepairError):
                journal.authorize_format(text)
            self.assertFalse(journal.data.get("format_consent_consumed", False))
            self.assertEqual(before, self.snapshot())
        journal.authorize_format("FORMAT DRIVE A ONCE")
        saved = json.loads((journal.directory / "state.json").read_text())
        self.assertIs(saved["format_consent_consumed"], True)
        self.assertEqual(saved["phase"], "format_pending")
        self.assertFalse((self.card / "autoexec.ash").exists())
        with self.assertRaises(self.w.RepairError):
            journal.authorize_format("FORMAT DRIVE A ONCE")

    def test_existing_session_never_becomes_a_fresh_repair(self):
        journal = self.journal()
        journal.data.update(phase="format_pending", format_consent_consumed=True)
        journal.save()
        before = self.snapshot()
        with self.assertRaises(self.w.RepairError):
            self.w.Journal.create(self.base / "private", self.card, self.identity)
        loaded = self.w.Journal.load(self.base / "private", self.card, self.identity)
        self.assertTrue(loaded.data["format_consent_consumed"])
        self.assertEqual(before, self.snapshot())

    def test_boot_markers_are_distinct_and_do_not_accept_echoed_commands(self):
        self.assertFalse(self.w.boot_ready(b"if mkdir c:\\NBFA01.claimed; then echo NBFA01_DRYRUN; else echo NBFA01_SKIP; fi\n", "dryrun"))
        self.assertTrue(self.w.boot_ready(b"NBFA01_DRYRUN\r\n", "dryrun"))
        self.assertTrue(self.w.boot_ready(b"NBFA01_SKIP\r\n", "rehearsal_skip"))
        with self.assertRaises(self.w.RepairError):
            self.w.boot_ready(b"NBFA01_DRYRUN\nNBFA01_SKIP\n", "rehearsal_skip")
        with self.assertRaises(self.w.RepairError):
            self.w.boot_ready(b"NBFA02_BEGIN\nNBFA02_BEGIN\nDrive 'A' format done.\n", "format")
        self.assertFalse(self.w.boot_ready(b"NBFA02_BEGIN\n", "format"))
        self.assertFalse(self.w.boot_ready(b"Drive 'A' format done.\n", "format"))
        self.assertTrue(self.w.boot_ready(b"NBFA02_BEGIN\nDrive 'A' format done.\n", "format"))
        with self.assertRaises(self.w.RepairError):
            self.w.boot_ready(b"NBFA02_BEGIN\nDrive 'A' format failed.\n", "format")
        with self.assertRaises(self.w.RepairError):
            self.w.boot_ready(b"NBFA02_SKIP\nNBFA02_BEGIN\nDrive 'A' format done.\n", "stock")

    def test_empty_native_claim_is_required_not_just_skip_text(self):
        with self.assertRaises(self.w.RepairError):
            self.w.require_empty_claim(self.card, "NBFA01.claimed")
        claim = self.card / "NBFA01.claimed"
        claim.mkdir()
        self.w.require_empty_claim(self.card, "NBFA01.claimed")
        (claim / "unexpected").write_bytes(b"not an empty native claim")
        with self.assertRaises(self.w.RepairError):
            self.w.require_empty_claim(self.card, "NBFA01.claimed")

    def test_snapshot_refuses_links_and_checks_readback_without_copying_recordings(self):
        source = self.card / "bt-nand-backup-1"
        source.mkdir()
        (source / "RESULT.txt").write_bytes(b"private result")
        self.w.snapshot_results(source, self.base / "saved")
        self.assertEqual((self.base / "saved/RESULT.txt").read_bytes(), b"private result")
        self.assertFalse((self.base / "saved/video.mp4").exists())
        (source / "link").symlink_to(self.card / "video.mp4")
        with self.assertRaises(self.w.RepairError):
            self.w.snapshot_results(source, self.base / "bad snapshot")

    def test_journal_rejects_modified_marker_and_unsafe_owned_names(self):
        journal = self.journal()
        marker = self.card / self.w.MARKER
        data = json.loads(marker.read_text())
        data["session"] = "../../outside"
        marker.write_text(json.dumps(data))
        with self.assertRaises(self.w.RepairError):
            self.w.Journal.load(self.base / "private", self.card, self.identity)
        journal.data["owned"] = {"../video.mp4": "0" * 64}
        with self.assertRaises(self.w.RepairError):
            self.w.clear_controls(self.card, journal)

    def test_format_publisher_itself_requires_consumed_consent(self):
        journal = self.journal()
        files = {"autoexec.ash": ROOT / "advanced/internal-drive-a/format-a-once.autoexec.ash"}
        with self.assertRaises(self.w.RepairError):
            self.w.stage_controls(self.card, journal, files, "format_armed")
        self.assertFalse((self.card / "autoexec.ash").exists())

    def test_source_changed_after_wizard_start_is_never_published(self):
        copied = self.base / "kit"
        shutil.copytree(ROOT / "advanced", copied / "advanced")
        shutil.copytree(ROOT / "persistent-repair/payload", copied / "persistent-repair/payload")
        wizard = self.w.Wizard(copied, volume=self.card, session_root=self.base / "private")
        wizard.journal = self.journal()
        wizard.journal.data["phase"] = "rehearsed"
        wizard.journal.authorize_format("FORMAT DRIVE A ONCE")
        hook = copied / "advanced/internal-drive-a/format-a-once.autoexec.ash"
        hook.write_bytes(b"format c:\n")
        with self.assertRaises(self.w.RepairError):
            wizard.stage(self.card, "format_armed", hook, ("usb.console",))
        self.assertFalse((self.card / "autoexec.ash").exists())

    def test_replaced_card_before_staging_or_removal_is_refused(self):
        journal = self.journal()
        self.w.stage_controls(self.card, journal, self.assets, "backup_staged")
        before = self.snapshot()
        marker = self.card / self.w.MARKER
        saved = marker.read_bytes()
        marker.write_bytes(b'{}\n')
        with self.assertRaises(self.w.RepairError):
            self.w.clear_controls(self.card, journal)
        marker.write_bytes(saved)
        self.assertEqual(self.snapshot(), before)
        self.w.clear_controls(self.card, journal)
        marker.write_bytes(b'{}\n')
        with self.assertRaises(self.w.RepairError):
            self.w.stage_controls(self.card, journal, self.assets, "backup_staged")
        self.assertFalse((self.card / "autoexec.ash").exists())

    def test_echoed_begin_does_not_prove_order_of_format_result(self):
        data = b"if mkdir x; then echo NBFA02_BEGIN; format a:; fi\nDrive 'A' format done.\nNBFA02_BEGIN\n"
        self.assertFalse(self.w.boot_ready(data, "format"))

    def test_live_capture_reader_is_bounded_but_allows_append(self):
        path = self.base / "growing.bin"
        path.write_bytes(b"NBFA02_BEGIN\n")
        with mock.patch.object(self.w, "read_regular", side_effect=AssertionError("immutable read used for live stream")):
            self.assertEqual(self.w.read_live_capture(path), b"NBFA02_BEGIN\n")
        with path.open("ab") as stream:
            stream.write(b"Drive 'A' format done.\n")
        self.assertTrue(self.w.boot_ready(self.w.read_live_capture(path), "format"))
        with self.assertRaises(self.w.RepairError):
            self.w.read_live_capture(path, limit=2)
        link = self.base / "linked.bin"
        link.symlink_to(path)
        with self.assertRaises(self.w.RepairError):
            self.w.read_live_capture(link)

    def wizard(self, approval="FORMAT DRIVE A ONCE", mutate=None):
        host = SyntheticHost(self.card, mutate)
        prompts = []
        def answer(prompt):
            prompts.append(prompt)
            if "To approve ONE" in prompt:
                self.assertNotEqual((self.card / "autoexec.ash").read_bytes(),
                                    (ROOT / "advanced/internal-drive-a/format-a-once.autoexec.ash").read_bytes())
                if approval is None:
                    raise EOFError()
                return approval
            if "Type YES:" in prompt:
                return "YES"
            return ""
        wizard = self.w.Wizard(ROOT, volume=self.card, session_root=self.base / "private",
                               host=host, ask=answer, say=lambda message: None)
        return wizard, host, prompts

    def test_complete_synthetic_workflow_verifies_results_and_cleans_controls(self):
        wizard, host, prompts = self.wizard()
        wizard.run()
        self.assertEqual(host.boots, ["backup", "dryrun", "rehearsal_skip", "format", "stock", "observer"])
        self.assertEqual(host.checks, 3)
        self.assertEqual(wizard.journal.data["phase"], "complete")
        self.assertTrue(wizard.journal.data["format_consent_consumed"])
        self.assertEqual(sum("pairing again" in p for p in prompts), 2)
        for name in self.w.CONTROL_NAMES:
            self.assertFalse((self.card / name).exists(), name)
        self.assertTrue((self.card / "NBFA01.claimed").is_dir())
        self.assertTrue((self.card / "NBFA02.claimed").is_dir())
        self.assertTrue((self.card / "bt-nand-backup-1/DRIVE_A-corrected-main.bin").exists())
        self.assertEqual((self.card / "video.mp4").read_bytes(), b"do not copy or erase")
        self.assertFalse(any(p.name == "video.mp4" for p in wizard.journal.directory.rglob("*")))

    def test_declining_or_eof_at_format_does_not_stage_or_consume_it(self):
        for approval in ("NO", None):
            with self.subTest(approval=approval):
                wizard, host, _ = self.wizard(approval)
                with self.assertRaises(self.w.RepairError):
                    wizard.run()
                self.assertFalse(wizard.journal.data["format_consent_consumed"])
                self.assertNotIn("format", host.boots)
                self.assertFalse((self.card / "NBFA02.claimed").exists())
                self.w.clear_controls(self.card, wizard.journal)
                # Preserve the first synthetic run outside the next run's card.
                if approval == "NO":
                    shutil.rmtree(self.card)
                    self.card.mkdir()
                    (self.card / "Nextbase.info").write_bytes(b"Model: 622GW\r\nFirmware: R13.3\r\n")

    def test_bad_backup_wrong_returned_card_and_new_hook_stop_before_approval(self):
        mutations = {
            "backup": lambda host: (host.card / "bt-nand-backup-1/helper-read-status.txt").write_bytes(b"TIMEOUT\n"),
            "card": lambda host: (host.card / "Nextbase.info").write_bytes(b"Model: 622GW\nFirmware: R13.3\nSerial: changed\n"),
            "hook": lambda host: (host.card / "autoexec.other.ash").write_bytes(b"unowned\n"),
        }
        for label, action in mutations.items():
            with self.subTest(label=label):
                def mutate(host, phase):
                    if phase == "backup": action(host)
                wizard, host, _ = self.wizard(mutate=mutate)
                with self.assertRaises(self.w.RepairError):
                    wizard.run()
                self.assertNotIn("format", host.boots)
                self.assertFalse(wizard.journal.data["format_consent_consumed"])
                shutil.rmtree(self.card); self.card.mkdir()
                (self.card / "Nextbase.info").write_bytes(b"Model: 622GW\r\nFirmware: R13.3\r\n")

    def test_missing_format_result_consumes_approval_and_relaunch_never_reboots_it(self):
        def mutate(host, phase):
            return b"NBFA02_BEGIN\n" if phase == "format" else None
        wizard, host, _ = self.wizard(mutate=mutate)
        with self.assertRaises(self.w.RepairError):
            wizard.run()
        self.assertTrue(wizard.journal.data["format_consent_consumed"])
        self.assertEqual(host.boots[-1], "format")
        before = self.snapshot()
        reopened, next_host, _ = self.wizard()
        reopened.run()
        self.assertEqual(next_host.boots, [])
        self.assertEqual(self.snapshot(), before)

    def test_format_staging_interruption_is_locked_against_reinstallation(self):
        wizard, host, _ = self.wizard()
        move = self.w.move_exclusive
        def fail_format(source, destination):
            if destination.name == "autoexec.ash" and source.read_bytes() == (ROOT / "advanced/internal-drive-a/format-a-once.autoexec.ash").read_bytes():
                raise OSError("injected interruption before publishing format hook")
            move(source, destination)
        with mock.patch.object(self.w, "move_exclusive", side_effect=fail_format):
            with self.assertRaises(OSError): wizard.run()
        self.assertTrue(wizard.journal.data["format_consent_consumed"])
        self.assertFalse((self.card / "autoexec.ash").exists())
        reopened, next_host, _ = self.wizard()
        reopened.run()
        self.assertEqual(next_host.boots, [])
        self.assertFalse((self.card / "autoexec.ash").exists())

    def test_preexisting_format_claim_is_refused_even_after_typed_consent(self):
        journal = self.journal()
        journal.data["phase"] = "rehearsed"
        journal.authorize_format("FORMAT DRIVE A ONCE")
        (self.card / "NBFA01.claimed").mkdir()
        (self.card / "NBFA02.claimed").mkdir()
        files = {"autoexec.ash": ROOT / "advanced/internal-drive-a/format-a-once.autoexec.ash"}
        with self.assertRaises(self.w.RepairError):
            self.w.stage_controls(self.card, journal, files, "format_armed")
        self.assertFalse((self.card / "autoexec.ash").exists())

    def test_unknown_controls_added_while_prompting_block_publication(self):
        journal = self.journal()
        for name in ("FW622GWA.bin", "usb.multi.console", "bt-legacy.sh", "nb-bt-recovery-kit.txt"):
            (self.card / name).write_bytes(b"unknown bytes")
            with self.subTest(name=name), self.assertRaises(self.w.RepairError):
                self.w.stage_controls(self.card, journal, self.assets, "backup_staged")
            self.assertFalse((self.card / "autoexec.ash").exists())
            (self.card / name).unlink()

    def test_bad_marker_shape_refuses_cleanly_without_traceback_or_writes(self):
        self.journal()
        for content in (b"[]", b"null", b'"not a marker"'):
            (self.card / self.w.MARKER).write_bytes(content)
            before = self.snapshot()
            with self.subTest(content=content), self.assertRaises(self.w.RepairError):
                self.w.Journal.load(self.base / "private", self.card, self.identity)
            self.assertEqual(self.snapshot(), before)

    def test_disk_checks_refuse_internal_readonly_or_wrong_filesystem(self):
        valid = {"Internal": False, "MountPoint": str(self.card), "FilesystemType": "exfat",
                 "WritableVolume": True, "WritableMedia": True}
        host = self.w.MacHost()
        for change in ({"Internal": True}, {"WritableVolume": False}, {"FilesystemType": "apfs"}, {"MountPoint": "/"}):
            response = mock.Mock(stdout=plistlib.dumps({**valid, **change}), returncode=0)
            with mock.patch.object(self.w.subprocess, "run", return_value=response):
                with self.subTest(change=change), self.assertRaises(self.w.RepairError): host.info(self.card)
        with mock.patch.object(self.w.subprocess, "run", return_value=mock.Mock(stdout=plistlib.dumps(valid), returncode=0)):
            host.info(self.card)
        with mock.patch.object(host, "info"), mock.patch.object(self.w.subprocess, "run", return_value=mock.Mock(returncode=1)) as command:
            with self.assertRaises(self.w.RepairError): host.verify(self.card)
            self.assertEqual(command.call_args.args[0][:2], ["/usr/sbin/diskutil", "verifyVolume"])

    @unittest.skipUnless(os.name == "posix", "POSIX passive capture fixture")
    def test_wizard_capture_receives_real_pty_without_transmitting(self):
        master, slave = pty.openpty()
        output = self.base / "passive-capture"
        error = []
        def produce():
            try:
                deadline = time.monotonic() + 5
                while not (output / "serial-rx.bin").exists():
                    if time.monotonic() > deadline: raise AssertionError("reader never opened")
                    time.sleep(0.01)
                os.write(master, b"NBFA02_BEGIN\n")
                time.sleep(0.3)
                os.write(master, b"Drive 'A' format done.\n")
            except BaseException as exc:
                error.append(exc)
        producer = threading.Thread(target=produce)
        producer.start()
        try:
            data = self.w.MacHost(os.ttyname(slave)).capture(ROOT / "tools/capture_rtos.py", output, "format")
            self.assertEqual(data, b"NBFA02_BEGIN\nDrive 'A' format done.\n")
            self.assertFalse(select.select([master], [], [], 0.05)[0], "wizard transmitted serial data")
            self.assertEqual(error, [])
            with self.assertRaises(self.w.RepairError):
                self.w.MacHost(os.ttyname(slave)).capture(ROOT / "tools/capture_rtos.py", output, "format")
        finally:
            producer.join(timeout=6)
            os.close(master); os.close(slave)


if __name__ == "__main__":
    unittest.main()
