"""Execute payload shell branches in a scratch device filesystem.

The real shell, hashing, file operations and guard logic run. Paths and the
vendor-binary allowlist are rebound to fixtures; only mount, signals, device
reads, timing and the native Amazon executable are simulated. No camera,
privileged mount, chroot or vendor binaries are required.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
PAYLOAD = REPO / "recovery-kit/payload"
OWNER = b"Nextbase622GW Bluetooth Recovery Kit 0.2.0\n"
TOKEN = b"PortableMultimediaLtdt/aNextbase"
VENDOR_HASHES = (
    "ea1ad4c2969abffee176364eef67e5df24b37598de18862ab5866eb86b64b054",
    "3fab6b79dc0becd8b4dd5f9c710989463661d6905f2e2e265d5a5377dea20747",
    "093bd3c261df7809ab30c77ca2d8d7870f5db66622d86d6125a17fd7295f6e55",
)
SYMPTOM = (b"Error opening/creating /tmp/FL0/bt_config.xml file\n"
           b"[amazon][app_mgr_config] Unable to Create defaul\n"
           b"t XML config file\n")

# This represents the native executable boundary, not recovered vendor code.
AMAZON = b'''#!/bin/sh
printf 'start-amazon\\n' >> "$HARNESS/actions"
printf '<generated-by-native-app/>\\n' > "$HARNESS/fl/bt_config.xml"
printf 'native app fixture ran\\n'
'''


class Device:
    def __init__(self, case):
        self.case = case
        self.tmp = tempfile.TemporaryDirectory()
        case.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for name in ("sd", "fl", "proc", "tmp", "dev", "bin", "vendor"):
            (self.root / name).mkdir()
        self.sd = self.root / "sd"
        self.fl = self.root / "fl"
        self.actions = self.root / "actions"
        self.actions.write_text("")
        self.amazon = self.root / "vendor/amazon_app"
        self.bsa = self.root / "vendor/bsa_server"
        self.hcd = self.root / "vendor/bt.hcd"
        self.amazon.write_bytes(AMAZON)
        self.amazon.chmod(0o755)
        self.bsa.write_bytes(b"fixture BSA binary\n")
        self.hcd.write_bytes(b"fixture controller HCD\n")
        self.expected_hashes = [self.digest(p) for p in (self.amazon, self.bsa, self.hcd)]
        (self.root / "tmp/amazon").symlink_to(self.amazon)
        self.process(226, "bsa_server", self.bsa)
        self.process(237, "amazon", self.amazon)
        (self.root / "dev/vcs").write_bytes(SYMPTOM)
        (self.root / "proc/uptime").write_text("25.00 40.00\n")
        (self.root / "proc/mounts").write_text(
            f"tmpfs {self.root}/tmp tmpfs rw 0 0\n"
            f"a: {self.fl} ambafs rw 0 0\n")
        (self.root / "proc/self").mkdir()
        (self.root / "proc/self/mountinfo").write_text("fixture mountinfo\n")
        (self.sd / "nb-bt-recovery-kit.txt").write_bytes(OWNER)
        (self.sd / "usb.console").write_bytes(TOKEN)
        (self.sd / "autoexec.ash").write_bytes(b"fixture installed hook\n")
        self.make_boundary_commands()

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def process(self, pid, comm, exe):
        p = self.root / f"proc/{pid}"
        p.mkdir(exist_ok=True)
        (p / "comm").write_text(comm + "\n")
        (p / "exe").symlink_to(exe)
        (p / "status").write_text(f"Name:\t{comm}\nState:\tS (sleeping)\n")

    def make_boundary_commands(self):
        helper = self.root / "bin/boundary"
        helper.write_text("#!" + shutil.which("python3") + "\n" + r'''
import hashlib, os, pathlib, shutil, sys, time
r = pathlib.Path(os.environ['HARNESS'])
cmd = pathlib.Path(sys.argv[0]).name
a = sys.argv[1:]
def action(s):
    with (r/'actions').open('a') as f: f.write(s+'\n')
if cmd == 'sha256sum':
    for name in a:
        try: print(hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()+'  '+name)
        except OSError: sys.exit(1)
elif cmd == 'mount':
    action('mount '+' '.join(a))
    if (r/'fail-mount').exists(): sys.exit(1)
    if len(a)!=3 or a[0]!='--bind': sys.exit(90)
    src,dst=map(pathlib.Path,a[1:])
    dst.rename(r/'underlay')
    dst.symlink_to(src, target_is_directory=True)
elif cmd == 'kill':
    sig,pid=a
    action('signal '+sig+' '+pid)
    p=r/'proc'/pid
    if (r/'replace-exe-on-term').exists() and sig=='-TERM':
        (p/'exe').unlink(); (p/'exe').symlink_to(r/'vendor/unrelated'); sys.exit(0)
    if sig=='-TERM' and (r/'ignore-term').exists(): sys.exit(0)
    if p.exists(): shutil.rmtree(p)
elif cmd == 'sleep':
    if a and a[0] in ('5', '15'):
        # Wait for the asynchronous fixture instead of racing a shortened clock.
        deadline=time.monotonic()+2
        while not (r/'fl/bt_config.xml').is_file():
            if time.monotonic()>=deadline: sys.exit(92)
            time.sleep(0.01)
    else: time.sleep(0.04)
elif cmd == 'id': print('0' if a==['-u'] else 'uid=0(root) gid=0(root)')
elif cmd == 'uname': print('armv7l' if a==['-m'] else '4.9.76')
elif cmd == 'ps': print('fixture process listing')
elif cmd == 'dmesg': print('fixture kernel log')
elif cmd == 'sync': pass
elif cmd == 'dd':
    kv=dict(x.split('=',1) for x in a)
    if (r/'fail-console-read').exists():
        sys.stdout.buffer.write(b'partial failed console read'); sys.exit(1)
    data=pathlib.Path(kv['if']).read_bytes()[:int(kv.get('bs',512))*int(kv.get('count',1))]
    if 'of' in kv: pathlib.Path(kv['of']).write_bytes(data)
    else: sys.stdout.buffer.write(data)
else: sys.exit(91)
''')
        helper.chmod(0o755)
        for name in ("sha256sum", "mount", "kill", "sleep", "id", "uname", "ps", "dmesg", "sync", "dd"):
            (self.root / "bin" / name).symlink_to(helper)

    def run(self):
        source = PAYLOAD / "nb-bt-recover.sh"
        self.case.assertTrue(source.is_file(), "Device payload has not been implemented")
        script = source.read_text()
        # Rebind only external paths and binary identity fixtures, keeping all
        # shell decisions and side effects in the actual payload implementation.
        mappings = {
            "/tmp/SD0": str(self.sd), "/tmp/FL0": str(self.fl),
            "/tmp/amazon": str(self.root / "tmp/amazon"),
            "/usr/bin/amazon_app": str(self.amazon),
            "/usr/bin/bsa_server": str(self.bsa),
            "/usr/local/bcmdhd/bt.hcd": str(self.hcd),
            "/bin/kill": str(self.root / "bin/kill"),
            "/proc": str(self.root / "proc"), "/dev/vcs": str(self.root / "dev/vcs"),
            "/tmp": str(self.root / "tmp"),
        }
        for i, (old, new) in enumerate(mappings.items()):
            script = script.replace(old, f"@@PATH{i}@@")
        for i, new in enumerate(mappings.values()):
            script = script.replace(f"@@PATH{i}@@", new)
        for old, new in zip(VENDOR_HASHES, self.expected_hashes):
            script = script.replace(old, new)
        script = script.replace("PATH=/bin:/sbin:/usr/bin:/usr/sbin",
                                f"PATH={self.root}/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        installed = self.sd / "nb-bt-recover.sh"
        if not installed.exists() or installed.read_text() != script:
            installed.write_text(script)
        env = dict(os.environ, HARNESS=str(self.root))
        return subprocess.run(["/bin/sh", str(installed)], env=env,
                              capture_output=True, text=True, timeout=10)

    def results(self):
        return sorted(self.sd.glob("nb-bt-recovery-[0-9]*"))


class PayloadTests(unittest.TestCase):
    def device(self):
        return Device(self)

    def assert_no_service_changes(self, d):
        self.assertEqual(d.actions.read_text(), "")
        self.assertFalse((d.sd / "nb-bt-recovery.claimed").exists())

    def test_rpc_stdout_is_nonempty_and_bounded_on_all_response_paths(self):
        # util_svc mishandles EOF on its unchecked first fgets. Catch a quiet
        # return or a later diagnostic accidentally leaking into RPC stdout.
        for mode, expected_code in (("attempt", 0), ("refusal", 20),
                                    ("owned-noop", 0), ("abort", 30)):
            with self.subTest(mode=mode):
                d = self.device()
                if mode == "refusal":
                    (d.sd / "nb-bt-recovery-kit.txt").unlink()
                elif mode == "owned-noop":
                    guard = d.sd / "nb-bt-recovery.claimed"
                    guard.mkdir()
                    (guard / "owner.txt").write_bytes(OWNER)
                    d.amazon.unlink(); d.bsa.unlink(); d.hcd.unlink()
                elif mode == "abort":
                    (d.root / "fail-mount").touch()
                result = d.run()
                self.assertEqual(result.returncode, expected_code,
                                 result.stdout + result.stderr)
                response = result.stdout.encode("ascii")
                self.assertGreater(len(response), 0, "RPC stdout must never be empty")
                self.assertLess(len(response), 511, "Keep RPC stdout below the RTOS display bound")
                self.assertTrue(response.endswith(b"\n"), "RPC needs a complete first line")
                self.assertEqual(len(response.splitlines()), 1,
                                 "Detailed diagnostics must stay in private files or stderr")

    def test_owned_claim_is_read_only_noop(self):
        d = self.device()
        guard = d.sd / "nb-bt-recovery.claimed"
        guard.mkdir(); (guard / "owner.txt").write_bytes(OWNER)
        d.run()  # Install the scratch copy before measuring card contents.
        d.amazon.unlink(); d.bsa.unlink(); d.hcd.unlink()
        before = {p.relative_to(d.sd): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in d.sd.rglob('*') if p.is_file()}
        result = d.run()
        after = {p.relative_to(d.sd): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in d.sd.rglob('*') if p.is_file()}
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, after)
        self.assertEqual(d.actions.read_text(), "")
        self.assertEqual(d.results(), [])

    def test_unknown_claim_owner_refuses_without_writes(self):
        d = self.device(); g = d.sd / "nb-bt-recovery.claimed"
        g.mkdir(); (g / "owner.txt").write_text("someone else's guard\n")
        result = d.run()
        self.assertEqual(result.returncode, 20)
        self.assertEqual(d.actions.read_text(), "")
        self.assertEqual(d.results(), [])

    def test_changed_vendor_binary_refuses_before_claim_or_mount(self):
        for field in ("amazon", "bsa", "hcd"):
            with self.subTest(field=field):
                d = self.device(); getattr(d, field).write_bytes(b"different build")
                self.assertEqual(d.run().returncode, 20)
                self.assert_no_service_changes(d)

    def test_missing_failure_signature_refuses_before_claim(self):
        d = self.device(); (d.root / "dev/vcs").write_text("normal camera boot\n")
        self.assertEqual(d.run().returncode, 20)
        self.assert_no_service_changes(d)

    def test_failed_partial_console_read_cannot_authorize_attempt(self):
        d = self.device(); (d.root / "fail-console-read").touch()
        self.assertEqual(d.run().returncode, 20)
        self.assert_no_service_changes(d)

    def test_unrelated_same_name_executable_is_never_signalled(self):
        d = self.device(); d.process(500, "amazon", d.root / "vendor/unrelated")
        self.assertEqual(d.run().returncode, 20)
        self.assert_no_service_changes(d)
        self.assertTrue((d.root / "proc/500").is_dir())

    def test_exact_bsa_is_required(self):
        d = self.device(); shutil.rmtree(d.root / "proc/226")
        self.assertEqual(d.run().returncode, 20)
        self.assert_no_service_changes(d)

    def test_mount_failure_never_stops_amazon(self):
        d = self.device(); (d.root / "fail-mount").touch()
        self.assertEqual(d.run().returncode, 30)
        self.assertTrue((d.root / "proc/237").is_dir())
        self.assertNotIn("signal", d.actions.read_text())
        self.assertNotIn("start-amazon", d.actions.read_text())
        self.assertTrue((d.results()[0] / "ABORTED.txt").is_file())
        result = d.results()[0] / "RESULT.txt"
        self.assertTrue(result.is_file(), "Attempt failure must have a user-readable result")
        self.assertIn("ABORTED", result.read_text())
        self.assertIn("RAM bind failed", result.read_text())

    def test_attempt_uses_ram_and_preserves_original_storage(self):
        d = self.device(); (d.fl / "bt_devices.xml").write_text("original pairing bytes\n")
        result = d.run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = d.results()[0]
        self.assertTrue((out / "ATTEMPT_COMPLETE.txt").is_file())
        result_file = out / "RESULT.txt"
        self.assertTrue(result_file.is_file(), "Attempt completion must have a user-readable result")
        self.assertIn("ATTEMPT_COMPLETE", result_file.read_text())
        self.assertIn("pairing", result_file.read_text())
        self.assertFalse((out / "SUCCESS.txt").exists())
        self.assertEqual((out / "bt_config.xml").read_text(), "<generated-by-native-app/>\n")
        self.assertFalse((d.root / "underlay/bt_config.xml").exists())
        self.assertEqual((d.root / "underlay/bt_devices.xml").read_text(), "original pairing bytes\n")
        self.assertEqual((out / "original-bt_devices.xml").read_text(), "original pairing bytes\n")
        self.assertEqual((out / "bt_devices.xml").read_text(), "original pairing bytes\n")
        self.assertTrue((out / "usb.console.used").is_file())
        self.assertFalse((d.sd / "usb.console").exists())
        self.assertEqual(list((d.sd / "nb-bt-recovery.claimed").iterdir()),
                         [d.sd / "nb-bt-recovery.claimed/owner.txt"])
        actions = d.actions.read_text().splitlines()
        self.assertTrue(actions[0].startswith("mount --bind "))
        self.assertEqual(actions[1:], ["signal -TERM 237", "start-amazon"])
        self.assertTrue((d.root / "proc/226").is_dir())

    def test_native_fixture_startup_can_outlive_accelerated_mock_sleep(self):
        d = self.device()
        original = d.amazon.read_bytes()
        d.amazon.write_bytes(original.replace(b"#!/bin/sh\n", b"#!/bin/sh\n/bin/sleep 0.5\n", 1))
        d.expected_hashes[0] = d.digest(d.amazon)
        result = d.run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((d.results()[0] / "bt_config.xml").read_text(), "<generated-by-native-app/>\n")

    def test_term_stall_kills_only_exact_amazon(self):
        d = self.device(); (d.root / "ignore-term").touch()
        self.assertEqual(d.run().returncode, 0)
        self.assertIn("signal -KILL 237", d.actions.read_text())
        self.assertNotIn("226", d.actions.read_text())

    def test_pid_replacement_is_not_killed_or_restarted(self):
        d = self.device(); (d.root / "replace-exe-on-term").touch()
        self.assertEqual(d.run().returncode, 30)
        self.assertNotIn("-KILL", d.actions.read_text())
        self.assertNotIn("start-amazon", d.actions.read_text())

    def test_unknown_console_token_is_not_consumed(self):
        d = self.device(); (d.sd / "usb.console").write_text("unknown hook\n")
        self.assertEqual(d.run().returncode, 20)
        self.assertEqual((d.sd / "usb.console").read_text(), "unknown hook\n")
        self.assert_no_service_changes(d)

    def test_missing_console_token_refuses_without_claim(self):
        d = self.device(); (d.sd / "usb.console").unlink()
        self.assertEqual(d.run().returncode, 20)
        self.assert_no_service_changes(d)

    def test_changed_host_owner_refuses_without_claim(self):
        d = self.device(); (d.sd / "nb-bt-recovery-kit.txt").write_bytes(OWNER + b"\n")
        self.assertEqual(d.run().returncode, 20)
        self.assert_no_service_changes(d)

    def test_sd_token_symlink_refuses_even_when_bytes_match(self):
        d = self.device(); token = d.sd / "usb.console"
        token.unlink(); original = d.root / "external-token"
        original.write_bytes(TOKEN); token.symlink_to(original)
        self.assertEqual(d.run().returncode, 20)
        self.assertEqual(original.read_bytes(), TOKEN)
        self.assert_no_service_changes(d)

    def test_non_ram_temporary_storage_refuses_before_mount(self):
        d = self.device(); mounts = d.root / "proc/mounts"
        mounts.write_text(f"/dev/root {d.root}/tmp ext4 rw 0 0\na: {d.fl} ambafs rw 0 0\n")
        self.assertEqual(d.run().returncode, 20)
        self.assert_no_service_changes(d)

    def test_configuration_symlink_refuses_before_mount(self):
        d = self.device(); (d.fl / "bt_devices.xml").symlink_to(d.hcd)
        self.assertEqual(d.run().returncode, 20)
        self.assert_no_service_changes(d)

    def test_payload_encoding_and_verified_token(self):
        for name in ("autoexec.ash", "nb-bt-recover.sh", "usb.console"):
            self.assertTrue((PAYLOAD / name).is_file(), f"Missing payload artifact: {name}")
        self.assertEqual((PAYLOAD / "usb.console").read_bytes(), TOKEN)
        self.assertEqual(Device.digest(PAYLOAD / "usb.console"),
                         "2b19515c1ee1515adc54d58c62cac67679ad3493185cddfe92e5872a5a8527f3")
        for name in ("autoexec.ash", "nb-bt-recover.sh"):
            content = (PAYLOAD / name).read_bytes()
            self.assertTrue(content.isascii()); self.assertNotIn(b'\r', content)
            self.assertTrue(content.endswith(b'\n'))
        checked = subprocess.run(["/bin/sh", "-n", str(PAYLOAD / "nb-bt-recover.sh")], capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
