"""Synthetic saved-result checks; these tests never open a camera or serial port."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "persistent-repair" / "results.py"
ADVANCED = ROOT / "advanced" / "internal-drive-a"
VENDOR = {
    "amazon_sha256": "ea1ad4c2969abffee176364eef67e5df24b37598de18862ab5866eb86b64b054",
    "bsa_sha256": "3fab6b79dc0becd8b4dd5f9c710989463661d6905f2e2e265d5a5377dea20747",
    "hcd_sha256": "093bd3c261df7809ab30c77ca2d8d7870f5db66622d86d6125a17fd7295f6e55",
}
HASHED = (
    "DRIVE_A-corrected-main.bin", "DRIVE_A-raw-main.bin", "DRIVE_A-raw-oob.bin",
    "DRIVE_A-badblocks.tsv", "read-status.tsv", "helper-summary.txt",
    "helper-ecc-before.txt", "helper-ecc-after.txt",
)
STATUSES = (
    "helper-copy", "local-before", "sysfs-before", "dmesg-before", "helper-read",
    "local-after", "sysfs-after", "dmesg-after", "capture-hashes", "verify-hashes", "sync-output",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PersistentResultTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), "Saved-result verification is not implemented")
        spec = importlib.util.spec_from_file_location("persistent_results", MODULE)
        self.result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.result)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.hook = b"synthetic preflight hook\n"
        self.script = b"synthetic preflight script\n"
        self.identity = b"Model: 622GW\nFirmware: R13.3\n"

    def write(self, name, data):
        (self.folder / name).write_bytes(data if isinstance(data, bytes) else data.encode())

    def manifest(self, name, files, absolute=False):
        prefix = "/tmp/SD0/bt-nand-backup-1/" if absolute else ""
        self.write(name, "".join(sha((self.folder / f).read_bytes()) + "  " + prefix + f + "\n" for f in files))
        if name == "capture.sha256":
            self.write("capture-hashes.txt", (self.folder / name).read_bytes())

    def preflight(self):
        fields = dict(model="622GW", firmware=getattr(self, "firmware", "R13.3"), machine="armv7l", kernel=getattr(self, "kernel", "4.9.76"),
                      **getattr(self, "vendor_hashes", VENDOR), identity_sha256=getattr(self, "identity_hash", sha(self.identity)), script_sha256=sha(self.script),
                      hook_sha256=sha(self.hook), fl_mount="ambafs_a", failure="BT_DEFAULT_CONFIG_CREATE_FAILED")
        self.write("RESULT.txt", "PREFLIGHT_VERIFIED\n" + "".join(k + "=" + v + "\n" for k, v in fields.items()))
        self.write("failure-console.bin", b"bt_config.xml\nUnable to Create default configuration\n")
        self.write("mounts.txt", "tmpfs /tmp tmpfs rw 0 0\na: /tmp/FL0 ambafs rw 0 0\n")
        self.manifest("SHA256SUMS", ("RESULT.txt", "failure-console.bin", "mounts.txt"))

    def verify_preflight(self):
        self.result.verify_preflight(self.folder, sha(self.identity), sha(self.hook), sha(self.script), getattr(self, "firmware", "R13.3"))

    def backup(self):
        self.write("RESULT.txt", "PARTITION_CAPTURE_VERIFIED\nreason=all selected-partition components, statuses, lengths and hashes verified\nrestorable_nand_backup=no\nfull_nand_backup=no\nOnly the selected DRIVE_A partition was requested; no repair or internal write was attempted.\nA timed-out child may remain until reboot; its partial files may still change.\n")
        self.write("CAPTURE_FINISHED.txt", "Wrapper reached its final step; inspect RESULT.txt and per-command statuses.\n")
        self.write("wrapper-errors.txt", "")
        for name, size in ((HASHED[0], 12058624), (HASHED[1], 12058624), (HASHED[2], 753664)):
            with (self.folder / name).open("wb") as stream:
                stream.truncate(size)
        self.write("DRIVE_A-badblocks.tsv", "offset\tis_bad\terrno\n" + "".join(f"{i * 131072}\t0\t0\n" for i in range(92)))
        rows = ["component\toffset\trequested\treturned\terrno\tcorrected_bits\tecc_failures\n"]
        for component, count, step, amount in (("corrected-main", 184, 65536, 65536), ("raw-main", 184, 65536, 65536), ("raw-oob", 5888, 2048, 128)):
            rows.extend(f"{component}\t{i * step}\t{amount}\t{amount}\t0\t0\t0\n" for i in range(count))
        self.write("read-status.tsv", "".join(rows))
        summary = dict(component="complete", reason="all components completed", errno="0", corrected_main_bytes="12058624", raw_main_bytes="12058624", raw_oob_bytes="753664", badblock_records="92", ecc_corrected_before="0", ecc_corrected_after="4", ecc_failures_before="0", ecc_failures_after="0", restorable_nand_backup="no", full_nand_backup="no")
        self.write("helper-summary.txt", "COMPLETE\n" + "".join(k + "=" + v + "\n" for k, v in summary.items()))
        for side in ("before", "after"):
            self.write("helper-ecc-" + side + ".txt", "corrected=" + ("4" if side == "after" else "0") + "\nfailed=0\nbadblocks=0\nbbtblocks=0\n")
        for name in STATUSES:
            self.write(name + "-status.txt", "exit_status=0\n")
            self.write(name + ".txt", "synthetic metadata\n" if name.startswith(("local-", "dmesg-")) else "")
        geometry = dict(name="DRIVE_A", type="nand", size="12058624", erasesize="131072", writesize="2048", oobsize="128", offset="203685888", flags="0x400", dev="90:18", ecc_strength="8", ecc_step_size="512", bitflip_threshold="6", corrected_bits="0", ecc_failures="0", bad_blocks="0", bbt_blocks="0")
        for side in ("before", "after"):
            self.write("sysfs-" + side + ".txt", "".join(k + "=" + v + "\n" for k, v in geometry.items()))
        helper_hash = sha((ADVANCED / "nb-mtd-readonly").read_bytes())
        wrapper_hash = sha((ADVANCED / "bt-nand-backup.sh").read_bytes())
        self.write("helper-provenance.txt", f"source=/tmp/SD0/nb-mtd-readonly\nsource_sha256={helper_hash}\nram_executable=/tmp/nb-mtd-readonly-123/nb-mtd-readonly\nram_sha256={helper_hash}\nwrapper_sha256={wrapper_hash}\nautoexec_sha256={sha(self.hook)}\nSource helper remains in SD root; no duplicate binary is stored in this result directory.\n")
        for source, target in (("bt-nand-backup.sh", "bt-nand-backup.sh.source"), ("nb-mtd-readonly.sha256", "nb-mtd-readonly.sha256.source"), ("usb.console", "usb.console.used")):
            self.write(target, (ADVANCED / source).read_bytes())
        self.write("autoexec.ash.source", self.hook)
        self.manifest("capture.sha256", HASHED, absolute=True)
        self.write("capture-hashes.txt", (self.folder / "capture.sha256").read_bytes())

    def persistence(self):
        self.write("RESULT.txt", "collection_exit_status=0\nRead-only observation; inspect context, per-file statuses and hashes.\nNo pairing or persistence success is established by this marker.\nsync_exit_status=0\n")
        for label in ("collect", "sync-output"):
            self.write(label + "-status.txt", "exit_status=0\n")
            self.write(label + ".txt", "")
        self.write("context.txt", "a: /tmp/FL0 ambafs rw 0 0\na: /pref ambafs rw 0 0\n12 1 0:1 / /tmp/FL0 rw - ambafs a: rw\n13 1 0:1 /pref//deleted /pref rw - ambafs a: rw\nmount_context_status=0\ndirectory_listing_status=0\n")
        self.write("bt_config.xml", '<X_BROADCOM_COM_BluetoothAdapter><bt_config><enable>1</enable><bd_addr>12:34:56:78:90:AB</bd_addr></bt_config></X_BROADCOM_COM_BluetoothAdapter>')
        self.write("bt_devices.xml", '<X_BROADCOM_COM_BluetoothAdapter><bt_devices><device value="0"><device_name>Synthetic Phone</device_name><bd_addr>AB:CD:EF:12:34:56</bd_addr><Link_key_present>1</Link_key_present><link_key>' + ':'.join(['11'] * 16) + '</link_key></device></bt_devices></X_BROADCOM_COM_BluetoothAdapter>')
        for name in ("bt_config.xml", "bt_devices.xml"):
            self.xml_hash(name)
        for name in ("si_devices.xml", "bt.conf"):
            self.write(name + ".status.txt", "MISSING (optional)\n")

    def xml_hash(self, name):
        self.write(name + ".status.txt", "COPIED bytes=" + str((self.folder / name).stat().st_size) + "\n")
        self.write(name + ".sha256", sha((self.folder / name).read_bytes()) + "  /tmp/SD0/bt-persistence-capture-1/" + name + "\n")

    def test_regular_reads_are_bounded_and_reject_missing_directory_and_links(self):
        self.write("regular", b"abcd")
        self.assertEqual(self.result.read_regular(self.folder / "regular", limit=4), b"abcd")
        self.assertEqual(self.result.digest(self.folder / "regular"), sha(b"abcd"))
        (self.folder / "linked").symlink_to(self.folder / "regular")
        for path in (self.folder / "missing", self.folder, self.folder / "linked"):
            with self.subTest(path=path.name), self.assertRaises(self.result.RepairError):
                self.result.read_regular(path)
        with self.assertRaises(self.result.RepairError):
            self.result.read_regular(self.folder / "regular", limit=3)

    def test_parent_directory_symlinks_are_refused(self):
        (self.folder / "real").mkdir(); (self.folder / "real/file").write_bytes(b"x")
        (self.folder / "linked").symlink_to(self.folder / "real", target_is_directory=True)
        with self.assertRaises(self.result.RepairError):
            self.result.read_regular(self.folder / "linked/file")

    def test_frozen_advanced_files_and_manifest_verify(self):
        self.result.verify_advanced(ADVANCED)
        self.assertEqual(len(self.result.ADVANCED_HASHES), 11)

    def test_modified_assets_and_forged_manifest_are_refused(self):
        target = self.folder / "assets"; shutil.copytree(ADVANCED, target)
        (target / "format-a-once.autoexec.ash").write_bytes(b"unreviewed format")
        manifest = (target / "SHA256SUMS").read_text().replace(self.result.ADVANCED_HASHES["format-a-once.autoexec.ash"], sha(b"unreviewed format"))
        (target / "SHA256SUMS").write_text(manifest)
        with self.assertRaises(self.result.RepairError):
            self.result.verify_advanced(target)

    def test_complete_preflight_verifies(self):
        self.preflight(); self.verify_preflight()

    def test_other_firmware_kernel_and_vendor_hashes_are_evidence_not_allowlists(self):
        for firmware in ("R10.0", "R13.2", "R15.1-beta + test"):
            self.firmware = firmware
            self.kernel = "6.6.0-custom"
            self.vendor_hashes = {key: sha((key + firmware).encode()) for key in VENDOR}
            self.preflight(); self.verify_preflight()

    def test_malformed_runtime_metadata_and_vendor_hashes_are_refused(self):
        for old, replacement in (("kernel=4.9.76", "kernel="), ("kernel=4.9.76", "kernel=bad kernel"),
                                 (VENDOR["amazon_sha256"], "bad"), (VENDOR["hcd_sha256"], "0" * 64)):
            self.preflight(); data=(self.folder / "RESULT.txt").read_text().replace(old, replacement)
            self.write("RESULT.txt", data); self.manifest("SHA256SUMS", ("RESULT.txt", "failure-console.bin", "mounts.txt"))
            with self.assertRaises(self.result.RepairError): self.verify_preflight()

    def test_preflight_changed_identity_duplicate_field_and_foreign_build_refuse(self):
        self.preflight(); original = (self.folder / "RESULT.txt").read_text()
        for text in (original + "model=622GW\n", original.replace("firmware=R13.3", "firmware=R14"), original.replace(sha(self.identity), "0" * 64)):
            self.write("RESULT.txt", text); self.manifest("SHA256SUMS", ("RESULT.txt", "failure-console.bin", "mounts.txt"))
            with self.subTest(text=text[:20]), self.assertRaises(self.result.RepairError):
                self.verify_preflight()

    def test_preflight_missing_failure_ram_overlay_and_duplicate_manifest_refuse(self):
        for name, data in (("failure-console.bin", b"bt_config.xml missing only"), ("mounts.txt", b"tmpfs /tmp/FL0 tmpfs rw 0 0\n"), ("mounts.txt", b"a: /tmp/FL0 ambafs rw 0 0\ntmpfs /tmp/FL0 tmpfs rw 0 0\n")):
            self.preflight(); self.write(name, data); self.manifest("SHA256SUMS", ("RESULT.txt", "failure-console.bin", "mounts.txt"))
            with self.subTest(name=name), self.assertRaises(self.result.RepairError): self.verify_preflight()
        self.preflight(); self.write("SHA256SUMS", (self.folder / "SHA256SUMS").read_bytes() * 2)
        with self.assertRaises(self.result.RepairError): self.verify_preflight()

    def test_preflight_oversized_console_and_linked_evidence_refuse(self):
        self.preflight(); self.write("failure-console.bin", b"bt_config.xml Unable to Create default" + b"x" * 16384)
        self.manifest("SHA256SUMS", ("RESULT.txt", "failure-console.bin", "mounts.txt"))
        with self.assertRaises(self.result.RepairError): self.verify_preflight()
        self.preflight(); (self.folder / "mounts.txt").rename(self.folder / "real-mounts")
        (self.folder / "mounts.txt").symlink_to(self.folder / "real-mounts")
        with self.assertRaises(self.result.RepairError): self.verify_preflight()

    def test_complete_selected_partition_backup_verifies(self):
        self.backup(); self.result.verify_backup(self.folder, sha(self.hook))

    def test_backup_short_data_missing_status_and_timeout_refuse(self):
        self.backup()
        for name, data in (("DRIVE_A-raw-oob.bin", b"short"), ("helper-read-status.txt", b"TIMEOUT\n"), ("helper-copy-status.txt", b"exit_status=1\n")):
            old = (self.folder / name).read_bytes(); self.write(name, data)
            with self.subTest(name=name), self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))
            self.write(name, old)
        (self.folder / "sysfs-after.txt").unlink()
        with self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))

    def test_backup_corrupt_coverage_even_with_rehashed_artifacts_refuses(self):
        self.backup()
        for name in ("DRIVE_A-badblocks.tsv", "read-status.tsv"):
            original = (self.folder / name).read_bytes()
            lines = original.splitlines(keepends=True); lines[-1] = lines[-2]
            self.write(name, b"".join(lines)); self.manifest("capture.sha256", HASHED, absolute=True)
            with self.subTest(name=name), self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))
            self.write(name, original)

    def test_backup_wrong_hook_and_duplicate_hash_record_refuse(self):
        self.backup()
        with self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, "0" * 64)
        self.write("capture.sha256", (self.folder / "capture.sha256").read_bytes() * 2)
        with self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))

    def test_backup_changed_frozen_source_refuses(self):
        self.backup(); self.write("bt-nand-backup.sh.source", b"changed")
        with self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))

    def test_backup_missing_error_log_and_oversized_numeric_record_refuse(self):
        self.backup(); (self.folder / "wrapper-errors.txt").unlink()
        with self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))
        self.write("wrapper-errors.txt", "")
        lines = (self.folder / "read-status.tsv").read_text().splitlines()
        columns = lines[1].split("\t"); columns[5] = "9" * 5000; lines[1] = "\t".join(columns)
        self.write("read-status.tsv", "\n".join(lines) + "\n"); self.manifest("capture.sha256", HASHED, absolute=True)
        with self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))

    def test_backup_contradictory_ecc_partial_data_and_linked_source_refuse(self):
        self.backup(); original = (self.folder / "helper-ecc-after.txt").read_bytes()
        self.write("helper-ecc-after.txt", original.replace(b"corrected=4", b"corrected=5")); self.manifest("capture.sha256", HASHED, absolute=True)
        with self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))
        self.write("helper-ecc-after.txt", original); self.manifest("capture.sha256", HASHED, absolute=True)
        self.write("unexpected.partial", b"incomplete")
        with self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))
        (self.folder / "unexpected.partial").unlink()
        (self.folder / "bt-nand-backup.sh.source").unlink()
        (self.folder / "bt-nand-backup.sh.source").symlink_to(ADVANCED / "bt-nand-backup.sh")
        with self.assertRaises(self.result.RepairError): self.result.verify_backup(self.folder, sha(self.hook))

    def test_complete_observer_with_optional_missing_files_verifies(self):
        self.persistence(); self.result.verify_persistence(self.folder)

    def test_observer_requires_real_mountinfo_and_no_ram_overlay(self):
        self.persistence(); original = (self.folder / "context.txt").read_text()
        for text in (original.replace("- ambafs a:", "- tmpfs tmpfs"), original.replace("12 1 0:1 / /tmp/FL0 rw - ambafs a: rw\n", ""), original + "14 1 0:1 / /tmp/FL0 rw - tmpfs tmpfs rw\n"):
            self.write("context.txt", text)
            with self.subTest(text=text[:20]), self.assertRaises(self.result.RepairError): self.result.verify_persistence(self.folder)

    def test_observer_unpaired_or_zero_adapter_cannot_establish_persistence(self):
        self.persistence()
        for name, old, new in (("bt_config.xml", "12:34:56:78:90:AB", "00:00:00:00:00:00"), ("bt_devices.xml", "<Link_key_present>1", "<Link_key_present>0"), ("bt_devices.xml", ':'.join(['11'] * 16), ':'.join(['00'] * 16))):
            original = (self.folder / name).read_bytes(); self.write(name, original.decode().replace(old, new)); self.xml_hash(name)
            with self.subTest(name=name), self.assertRaises(self.result.RepairError): self.result.verify_persistence(self.folder)
            self.write(name, original); self.xml_hash(name)

    def test_observer_failed_collection_hash_tamper_and_missing_required_file_refuse(self):
        self.persistence(); self.write("collect-status.txt", "exit_status=1\n")
        with self.assertRaises(self.result.RepairError): self.result.verify_persistence(self.folder)
        self.persistence(); self.write("bt_config.xml", "changed")
        with self.assertRaises(self.result.RepairError): self.result.verify_persistence(self.folder)
        self.persistence(); (self.folder / "bt_devices.xml").unlink()
        with self.assertRaises(self.result.RepairError): self.result.verify_persistence(self.folder)

    def test_xml_errors_do_not_print_private_values(self):
        self.persistence(); self.write("bt_devices.xml", "PRIVATE_PAIRING_SECRET malformed <"); self.xml_hash("bt_devices.xml")
        with self.assertRaises(self.result.RepairError) as error: self.result.verify_persistence(self.folder)
        self.assertNotIn("PRIVATE_PAIRING_SECRET", str(error.exception))

    def test_observer_rejects_non_utf8_xml_even_when_hashes_verify(self):
        self.persistence(); original = (self.folder / "bt_config.xml").read_text()
        self.write("bt_config.xml", original.encode("utf-16")); self.xml_hash("bt_config.xml")
        with self.assertRaises(self.result.RepairError): self.result.verify_persistence(self.folder)


if __name__ == "__main__":
    unittest.main()
