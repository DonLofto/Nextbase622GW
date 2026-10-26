"""Run the read-only preflight against a scratch device, never a camera."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "persistent-repair/payload"
BACKUP_HASH = "5492a73791eedf4ede299bf5c407cb5dd4beaf3b71c1b64edc585aab73e9072e"
TOKEN = b"PortableMultimediaLtdt/aNextbase"
SYMPTOM = (b"Error opening/creating /tmp/FL0/bt_config.xml file\n"
           b"[amazon][app_mgr_config] Unable to Create defaul\n"
           b"t XML config file\x00\n")
HOOK = b"sleep 30000\nt app linux_cmd /bin/sh /tmp/SD0/nb-a-preflight.sh\n"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Device:
    def __init__(self, case):
        case.assertTrue((PAYLOAD / "nb-a-preflight.sh").is_file(),
                        "read-only persistent preflight has not been implemented")
        temporary = tempfile.TemporaryDirectory(prefix="nb-preflight-test-")
        case.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for name in ("sd", "fl", "proc", "dev", "vendor", "bin", "tmp"):
            (self.root / name).mkdir()
        self.sd = self.root / "sd"
        self.fl = self.root / "fl"
        self.actions = self.root / "actions"
        self.actions.write_text("")
        self.vendor = [self.root / "vendor" / name for name in
                       ("amazon_app", "bsa_server", "bt.hcd")]
        for index, path in enumerate(self.vendor):
            path.write_bytes(f"fixture vendor {index}\n".encode())
            if index < 2: path.chmod(0o755)
        (self.root / "tmp/amazon").symlink_to(self.vendor[0])
        (self.sd / "Nextbase.info").write_bytes(
            b"NBDVR622GWA-R13.3\r\nModel: 622GW\r\nFirmware: R13.3\r\n"
            b"Serial No: PRIVATE-SENTINEL\r\nSD Card Serial No: A1B2C3D4\r\n")
        (self.sd / "usb.console").write_bytes(TOKEN)
        (self.sd / "autoexec.ash").write_bytes(HOOK)
        (self.fl / "keep.xml").write_bytes(b"unchanged internal data\n")
        (self.root / "dev/vcs").write_bytes(SYMPTOM)
        self.mounts = self.root / "proc/mounts"
        self.mounts.write_text(f"tmpfs {self.root}/tmp tmpfs rw 0 0\na: {self.fl} ambafs rw 0 0\n")
        self.backup = self.sd / "bt-nand-backup.sh"
        self.backup.write_text('#!/bin/sh\nprintf "backup\\n" >> "$HARNESS/actions"\nprintf "Backup fixture entered.\\n"\n')
        self.make_commands()
        text = (PAYLOAD / "nb-a-preflight.sh").read_text()
        paths = {
            "/tmp/SD0": self.sd, "/tmp/FL0": self.fl,
            "/tmp/amazon": self.root / "tmp/amazon",
            "/usr/bin/amazon_app": self.vendor[0],
            "/usr/bin/bsa_server": self.vendor[1],
            "/usr/local/bcmdhd/bt.hcd": self.vendor[2],
            "/proc": self.root / "proc", "/dev/vcs": self.root / "dev/vcs",
            "/tmp": self.root / "tmp",
        }
        for index, old in enumerate(paths):
            text = text.replace(old, f"@@PATH{index}@@")
        for index, path in enumerate(paths.values()):
            text = text.replace(f"@@PATH{index}@@", str(path))
        text = text.replace(BACKUP_HASH, digest(self.backup))
        text = text.replace("PATH=/bin:/sbin:/usr/bin:/usr/sbin",
                            f"PATH={self.root}/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        (self.sd / "nb-a-preflight.sh").write_text(text)

    def make_commands(self):
        boundary = self.root / "bin/boundary"
        boundary.write_text("#!" + shutil.which("python3") + "\n" + r'''
import hashlib, os, pathlib, sys
r=pathlib.Path(os.environ['HARNESS']); command=pathlib.Path(sys.argv[0]).name; args=sys.argv[1:]
if command == 'sha256sum':
    if not args: print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest()+'  -')
    for name in args:
        try:
            if (r/'fail-report-hash').exists() and pathlib.Path(name).name == 'RESULT.txt': sys.exit(1)
            print(hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()+'  '+name)
        except OSError: sys.exit(1)
elif command == 'id': print('501' if (r/'not-root').exists() else '0')
elif command == 'uname':
    if args==['-m']: print('x86_64' if (r/'wrong-machine').exists() else 'armv7l')
    else: print((r/'kernel').read_text() if (r/'kernel').exists() else '4.9.76')
elif command == 'sync':
    with (r/'actions').open('a') as f: f.write('sync\n')
elif command == 'dd':
    fields=dict(arg.split('=',1) for arg in args)
    try: data=pathlib.Path(fields['if']).read_bytes()[:int(fields.get('bs',512))*int(fields.get('count',1))]
    except OSError: sys.exit(1)
    if (r/'fail-console-read').exists(): sys.stdout.buffer.write(data); sys.exit(1)
    if 'of' in fields:
        if (r/'fail-console-save').exists(): sys.exit(1)
        pathlib.Path(fields['of']).write_bytes(data)
    else: sys.stdout.buffer.write(data)
else:
    with (r/'actions').open('a') as f: f.write('FORBIDDEN '+command+'\n')
    sys.exit(90)
''')
        boundary.chmod(0o755)
        for name in ("sha256sum", "id", "uname", "sync", "dd", "mount", "kill", "format", "reboot"):
            (self.root / "bin" / name).symlink_to(boundary)

    def run(self):
        return subprocess.run(["/bin/sh", str(self.sd / "nb-a-preflight.sh")],
                              env=dict(os.environ, HARNESS=str(self.root)),
                              capture_output=True, timeout=10)

    def snapshot(self):
        result = {}
        for path in self.sd.rglob("*"):
            relative = str(path.relative_to(self.sd))
            if path.is_symlink(): result[relative] = ("link", os.readlink(path))
            elif path.is_file(): result[relative] = (path.read_bytes(), path.stat().st_mtime_ns)
            else: result[relative] = ("directory",)
        return result


@unittest.skipUnless(os.name == "posix", "Camera shell fixture requires POSIX sh")
class PersistentPreflightTests(unittest.TestCase):
    def device(self):
        return Device(self)

    def test_identity_fingerprint_does_not_include_changing_status_fields(self):
        hashes = []
        for status in (b"Battery Status: 10%\nSD Card Used Space: 24MB\n", b"Battery Status: 100%\nSD Card Used Space: 56MB\n"):
            d = self.device()
            with (d.sd / "Nextbase.info").open("ab") as stream:
                stream.write(status)
            result = d.run()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            fields = dict(line.split("=", 1) for line in (d.sd / "nb-a-preflight/RESULT.txt").read_text().splitlines()[1:])
            hashes.append(fields["identity_sha256"])
        self.assertEqual(hashes[0], hashes[1])

    def refuses_unchanged(self, device):
        before = device.snapshot()
        result = device.run()
        self.assertEqual(result.returncode, 20, result.stdout + result.stderr)
        self.assertEqual(device.snapshot(), before)
        self.assertEqual(device.actions.read_text(), "")
        self.assertGreater(len(result.stdout), 0)
        self.assertLess(len(result.stdout), 511)
        self.assertIn(b"Drive A preflight refused:", result.stdout,
                      "The RTOS RPC exposes stdout, so refusal must be visible there")
        self.assertNotIn(b"PRIVATE-SENTINEL", result.stdout + result.stderr)

    def test_valid_preflight_preserves_raw_proof_then_invokes_backup(self):
        d = self.device()
        internal = (d.fl / "keep.xml").read_bytes()
        result = d.run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreater(len(result.stdout), 0); self.assertLess(len(result.stdout), 511)
        self.assertNotIn(b"PRIVATE-SENTINEL", result.stdout + result.stderr)
        self.assertEqual(d.actions.read_text().splitlines(), ["sync", "backup"])
        out = d.sd / "nb-a-preflight"
        self.assertEqual({p.name for p in out.iterdir()},
                         {"RESULT.txt", "failure-console.bin", "mounts.txt", "SHA256SUMS"})
        self.assertEqual((out / "failure-console.bin").read_bytes(), SYMPTOM)
        self.assertEqual((out / "mounts.txt").read_bytes(), d.mounts.read_bytes())
        lines = (out / "RESULT.txt").read_text().splitlines()
        self.assertEqual(lines[0], "PREFLIGHT_VERIFIED")
        fields = dict(line.split("=", 1) for line in lines[1:])
        self.assertEqual(len(fields), len(lines) - 1)
        self.assertEqual(fields, {
            "model": "622GW", "firmware": "R13.3", "machine": "armv7l", "kernel": "4.9.76",
            "amazon_sha256": digest(d.vendor[0]), "bsa_sha256": digest(d.vendor[1]),
            "hcd_sha256": digest(d.vendor[2]), "identity_sha256": hashlib.sha256(b"model=622GW\nfirmware=R13.3\nserial_no=PRIVATE-SENTINEL\nsd_serial_no=A1B2C3D4\n").hexdigest(),
            "script_sha256": digest(d.sd / "nb-a-preflight.sh"),
            "hook_sha256": digest(d.sd / "autoexec.ash"), "fl_mount": "ambafs_a",
            "failure": "BT_DEFAULT_CONFIG_CREATE_FAILED",
        })
        rows = (out / "SHA256SUMS").read_text().splitlines()
        self.assertEqual(len(rows), 3)
        names = []
        for line in rows:
            sha, name = line.split("  ", 1)
            self.assertEqual(sha, digest(out / name)); names.append(name)
        self.assertEqual(set(names), {"RESULT.txt", "failure-console.bin", "mounts.txt"})
        self.assertEqual((d.fl / "keep.xml").read_bytes(), internal)

    def test_wrong_identity_runtime_or_missing_vendor_refuses_before_sd_output(self):
        for mode in ("model", "firmware", "duplicate", "duplicate-serial", "missing-card-serial", "zero-serial", "not-root", "wrong-machine", "bad-kernel", "amazon", "bsa", "hcd"):
            with self.subTest(mode=mode):
                d = self.device()
                info = d.sd / "Nextbase.info"
                if mode == "model": info.write_bytes(b"Model: 522GW\nFirmware: R13.3\n")
                elif mode == "firmware": info.write_bytes(info.read_bytes().replace(b"R13.3", b""))
                elif mode == "duplicate": info.write_bytes(info.read_bytes() + b"MODEL: 622GW\n")
                elif mode == "duplicate-serial": info.write_bytes(info.read_bytes() + b"Serial No: OTHER\n")
                elif mode == "missing-card-serial": info.write_bytes(info.read_bytes().replace(b"SD Card Serial No: A1B2C3D4\r\n", b""))
                elif mode == "zero-serial": info.write_bytes(info.read_bytes().replace(b"A1B2C3D4", b"00000000"))
                elif mode == "bad-kernel": (d.root / "kernel").write_text("bad kernel")
                elif mode in ("amazon", "bsa", "hcd"): d.vendor[("amazon", "bsa", "hcd").index(mode)].unlink()
                else: (d.root / mode).touch()
                self.refuses_unchanged(d)

    def test_any_firmware_and_changed_vendor_build_are_recorded_without_version_gate(self):
        for firmware in ("R10.0", "R13.2", "R15.1-beta + test"):
            with self.subTest(firmware=firmware):
                d = self.device(); info = d.sd / "Nextbase.info"
                info.write_bytes(info.read_bytes().replace(b"R13.3", firmware.encode()))
                (d.root / "kernel").write_text("6.6.0-custom")
                for index, path in enumerate(d.vendor): path.write_bytes((firmware + str(index)).encode())
                result = d.run(); self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                fields = dict(line.split("=", 1) for line in (d.sd / "nb-a-preflight/RESULT.txt").read_text().splitlines()[1:])
                self.assertEqual(fields["firmware"], firmware)
                self.assertEqual(fields["kernel"], "6.6.0-custom")
                for name, path in zip(("amazon_sha256", "bsa_sha256", "hcd_sha256"), d.vendor): self.assertEqual(fields[name], digest(path))
                material = f"model=622GW\nfirmware={firmware}\nserial_no=PRIVATE-SENTINEL\nsd_serial_no=A1B2C3D4\n"
                self.assertEqual(fields["identity_sha256"], hashlib.sha256(material.encode()).hexdigest())
                self.assertEqual(d.actions.read_text().splitlines(), ["sync", "backup"])

    def test_backup_wrapper_accepts_any_firmware_before_checking_actual_storage(self):
        for firmware in ("R10.0", "R15.1-beta + test"):
            d = self.device(); info = d.sd / "Nextbase.info"
            info.write_bytes(info.read_bytes().replace(b"R13.3", firmware.encode()))
            (d.root / "kernel").write_text("6.6.0-custom")
            text = (ROOT / "advanced/internal-drive-a/bt-nand-backup.sh").read_text()
            for key, value in (("sd=/tmp/SD0", "sd=" + str(d.sd)), ("proc=/proc", "proc=" + str(d.root / "proc")),
                               ("sys=/sys", "sys=" + str(d.root / "sys")), ("tmp=/tmp", "tmp=" + str(d.root / "tmp"))):
                text = text.replace(key, value)
            text = text.replace("PATH=/bin:/sbin:/usr/bin:/usr/sbin", f"PATH={d.root}/bin:/usr/bin:/bin:/usr/sbin:/sbin")
            d.backup.write_text(text)
            helper = d.sd / "nb-mtd-readonly"; helper.write_bytes(b"fixture helper")
            (d.sd / "nb-mtd-readonly.sha256").write_text(digest(helper) + "  nb-mtd-readonly\n")
            before = d.snapshot()
            result = subprocess.run(["/bin/sh", str(d.backup)], env={**os.environ, "HARNESS": str(d.root)}, capture_output=True)
            self.assertEqual(result.returncode, 20)
            self.assertIn(b"proc MTD identity/geometry", result.stdout)
            self.assertEqual(d.snapshot(), before)
            self.assertFalse((d.sd / "bt-nand-backup.claimed").exists())

    def test_missing_out_of_range_or_failed_console_proof_is_refused(self):
        for mode in ("missing", "empty", "beyond-bound", "failed-read"):
            with self.subTest(mode=mode):
                d = self.device(); vcs = d.root / "dev/vcs"
                if mode == "missing": vcs.unlink()
                elif mode == "empty": vcs.write_bytes(b"")
                elif mode == "beyond-bound": vcs.write_bytes(b"x" * 16384 + SYMPTOM)
                else: (d.root / "fail-console-read").touch()
                self.refuses_unchanged(d)

    def test_console_fallback_and_capture_bound(self):
        d = self.device()
        (d.root / "dev/vcs").write_bytes(b"no failure here")
        data = SYMPTOM + b"x" * 20000
        (d.root / "dev/vcs1").write_bytes(data)
        result = d.run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((d.sd / "nb-a-preflight/failure-console.bin").read_bytes(), data[:16384])

    def test_missing_overlay_or_duplicate_internal_mount_is_refused(self):
        for line in ("", "tmpfs {fl} tmpfs rw 0 0\n", "a: {fl} ambafs rw 0 0\na: {fl} ambafs rw 0 0\n"):
            with self.subTest(line=line):
                d = self.device()
                d.mounts.write_text(f"tmpfs {d.root}/tmp tmpfs rw 0 0\n" + line.format(fl=d.fl))
                self.refuses_unchanged(d)

    def test_existing_output_or_backup_claim_blocks_all_writes(self):
        for name in ("nb-a-preflight", "bt-nand-backup.claimed"):
            for kind in ("directory", "file", "link"):
                with self.subTest(name=name, kind=kind):
                    d = self.device(); path = d.sd / name
                    if kind == "directory": path.mkdir()
                    elif kind == "file": path.write_bytes(b"preserve unknown result")
                    else: path.symlink_to(d.root / "missing")
                    self.refuses_unchanged(d)

    def test_linked_staged_or_vendor_files_are_refused(self):
        for name in ("Nextbase.info", "nb-a-preflight.sh", "autoexec.ash", "bt-nand-backup.sh", "usb.console", "amazon"):
            with self.subTest(name=name):
                d = self.device(); path = d.vendor[0] if name == "amazon" else d.sd / name
                target = d.root / "linked-target"; target.write_bytes(path.read_bytes())
                path.unlink(); path.symlink_to(target)
                self.refuses_unchanged(d)

    def test_changed_wrapper_token_or_update_file_is_refused(self):
        for mode in ("wrapper", "token", "firmware"):
            with self.subTest(mode=mode):
                d = self.device()
                if mode == "wrapper": d.backup.write_bytes(b"unreviewed wrapper\n")
                elif mode == "token": (d.sd / "usb.console").write_bytes(b"unknown")
                else: (d.sd / "FW622GWA.bin").write_bytes(b"do not flash")
                self.refuses_unchanged(d)

    def test_incomplete_proof_output_never_starts_backup(self):
        for marker in ("fail-console-save", "fail-report-hash"):
            with self.subTest(marker=marker):
                d = self.device(); (d.root / marker).touch()
                result = d.run()
                self.assertEqual(result.returncode, 30, result.stdout + result.stderr)
                self.assertNotIn("backup", d.actions.read_text())
                self.assertTrue((d.sd / "nb-a-preflight").is_dir())
                self.assertGreater(len(result.stdout), 0); self.assertLess(len(result.stdout), 511)
                self.assertIn(b"Drive A preflight incomplete:", result.stdout,
                              "The launcher must observe partial-proof failure without waiting")

    def test_second_run_preserves_evidence_and_does_not_repeat_backup(self):
        d = self.device()
        self.assertEqual(d.run().returncode, 0)
        before = d.snapshot(); actions = d.actions.read_text()
        result = d.run()
        self.assertEqual(result.returncode, 20)
        self.assertEqual(d.snapshot(), before)
        self.assertEqual(d.actions.read_text(), actions)

    def test_payload_manifest_and_native_hook_match_distributed_bytes(self):
        for name in ("preflight.autoexec.ash", "nb-a-preflight.sh", "SHA256SUMS"):
            self.assertTrue((PAYLOAD / name).is_file(), f"Missing preflight payload: {name}")
            content = (PAYLOAD / name).read_bytes()
            self.assertTrue(content.isascii()); self.assertNotIn(b"\r", content)
            self.assertTrue(content.endswith(b"\n"))
        self.assertEqual((PAYLOAD / "preflight.autoexec.ash").read_bytes(), HOOK)
        entries = (PAYLOAD / "SHA256SUMS").read_text().splitlines()
        self.assertEqual(len(entries), 2)
        names = []
        for line in entries:
            sha, name = line.split("  ", 1)
            self.assertEqual(sha, digest(PAYLOAD / name)); names.append(name)
        self.assertEqual(set(names), {"preflight.autoexec.ash", "nb-a-preflight.sh"})
        checked = subprocess.run(["/bin/sh", "-n", str(PAYLOAD / "nb-a-preflight.sh")], capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
