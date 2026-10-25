# Temporary Bluetooth recovery guide

Start with the [five-step quick start](../README.md#temporary-recovery-in-five-steps). This guide covers the **default temporary RAM recovery** in release **0.2.0**, not the separate [advanced internal Drive A repair](internal-storage-repair.md). Neither double-click launcher selects the advanced procedure.

The supported case is a **Nextbase 622GW / R13.3** whose vendor Bluetooth application fails to create its default `/tmp/FL0/bt_config.xml`. A zero MAC or failed pairing alone is insufficient. The installer checks model/firmware; the camera script checks runtime identities, known binary hashes, the specific configuration failure and an existing BSA service. Other models, firmware and faults are outside the tested scope. Do not bypass a check or install firmware solely to try this kit.

The original RAM operation restored discoverability and Nextbase app access on the examined camera. The guarded distribution has **not** been boot-tested end to end on a camera. Automated host/payload tests do not establish physical camera behavior. See [validation](technical-notes.md#validation).

## Verify the download

Download both `Nextbase622GW-recovery-0.2.0.zip` and `SHA256SUMS.txt` from the [0.2.0 release](https://github.com/DonLofto/Nextbase622GW/releases/tag/v0.2.0) into the same computer folder. Verify before extracting:

**macOS**, from that download folder:

```sh
shasum -a 256 -c SHA256SUMS.txt
```

Require the ZIP's result to be `OK`. On **Windows PowerShell**, from the same folder:

```powershell
Get-Content -LiteralPath .\SHA256SUMS.txt | ForEach-Object {
    $expected, $name = $_ -split '  ', 2
    if ((Get-FileHash -LiteralPath $name -Algorithm SHA256).Hash -ine $expected) {
        throw "Hash mismatch: $name"
    }
}
```

Any missing file, error or mismatch is a stop condition. Extract the entire ZIP onto the computer, outside the card. Keep the `recovery-kit` folder and its nested `payload` files together; do not run from inside the ZIP. A GitHub **Code → Download ZIP** source download is an alternative, but use the complete matching tree and its included manifests.

## Prepare the card and run

Save recordings you want to keep. Stop recording, fully power the camera off, and preferably use a working microSD reader. Alternatively, connect a USB **data** cable to the camera body's mini-USB port and choose **Firmware Update** for writable access. The mount's USB port is power only; **Access Files** was read-only on the tested camera. No firmware image is needed.

From the extracted kit, open:

| Computer | Launcher |
|---|---|
| macOS | `recovery-kit/Recover Bluetooth.command` |
| Windows | `recovery-kit/Recover Bluetooth.cmd` |

The tool finds a compatible card, verifies the manifest and files, and copies the owned startup hook, recovery script and diagnostic trigger. It refuses conflicting startup files or firmware update binaries. Follow a refusal instead of overwriting files. No administrator access, Python, firmware download or permanent PowerShell policy change is required for this temporary path.

Safely eject. Return the card to the powered-off camera; if using camera USB storage, power the camera off and unplug it. Reconnect the computer to the **camera body's USB data port**, turn it on, and wait a full minute. The USB diagnostic trigger may bypass the normal PC Connection menu; that is the boot route used in the demonstrated recovery.

Stop recording, choose **cog → Connected App → Setup phone → OK**, then pair using the Nextbase app. Require the app to show the camera or recordings. `ATTEMPT_COMPLETE` in a result file only confirms that the script finished an attempt; it does not prove discovery, pairing or app access. Keep the camera powered during this session.

## What the temporary operation changes

The script puts a fresh RAM directory over the **whole Linux `/tmp/FL0` path** and restarts only the vendor Amazon Bluetooth application. Other Linux processes opening that path also see RAM; this is not a per-process overlay.

Readable existing Bluetooth XML is copied into RAM and private diagnostic copies are saved on the card. The vendor application generates its own configuration, so no guessed Bluetooth XML is needed. BSA, radio firmware, UART and GPIO remain running. The temporary path does not flash firmware or intentionally write/format the underlying internal drive. Reboot discards the overlay and new configuration; pairing keys created in RAM can be lost. It does not install an every-boot SD-backed workaround. [Exact operation and identities](technical-notes.md#packaged-operation).

## Check, remove or re-arm

After stopping recording, power off the camera and put its card in a reader again. A successful run normally moves its own USB trigger into its result folder, allowing the normal USB menu on a later cold boot. If that menu does not return, use the reader.

Open Terminal or PowerShell in the **extracted release root**, then use the commands below. Replace `/Volumes/NEXTBASE` or `E:\` with the actual card path/letter. Omit the path only when exactly one compatible card is connected.

Run only the command for the action you want.

**macOS:**

| Action | Command |
|---|---|
| Check ownership | `bash recovery-kit/prepare-macos.sh status /Volumes/NEXTBASE` |
| Remove startup files | `bash recovery-kit/prepare-macos.sh remove /Volumes/NEXTBASE` |
| Prepare a session | `bash recovery-kit/prepare-macos.sh prepare /Volumes/NEXTBASE` |

**Windows PowerShell:**

| Action | Command |
|---|---|
| Check ownership | `powershell -NoProfile -ExecutionPolicy Bypass -File .\recovery-kit\prepare-windows.ps1 -Action Status -Volume E:\` |
| Remove startup files | `powershell -NoProfile -ExecutionPolicy Bypass -File .\recovery-kit\prepare-windows.ps1 -Action Remove -Volume E:\` |
| Prepare a session | `powershell -NoProfile -ExecutionPolicy Bypass -File .\recovery-kit\prepare-windows.ps1 -Action Prepare -Volume E:\` |

Use **Status** to inspect ownership. Use **Remove** to remove the kit's startup files. For another session, run **Remove, then Prepare**, safely eject, and repeat the startup/pairing steps. The one-shot claim prevents rerunning automatically on subsequent boots, including when exporting the card over USB.

Remove preserves recordings and `nb-bt-recovery-*` result folders and refuses to delete modified or unowned files. The temporary installer does not prepare or remove the advanced repair procedure.

To upgrade a card prepared with an older kit, first remove it with **that matching version's tool**, then prepare with 0.2.0. Ownership markers include the version; a different version is refused rather than overwritten.

If removing by hand, remove only this kit's verified owned root files/directories:

```text
autoexec.ash
nb-bt-recover.sh
usb.console                 (if still present)
nb-bt-recovery-kit.txt
nb-bt-recovery.claimed/     (directory)
```

Do not delete another tool's startup files or unknown files. Safely eject afterward. A reboot removes the RAM overlay.

## Troubleshooting

| Problem | What to do |
|---|---|
| No card found | Use a reader or the body's data port with **Firmware Update** selected. Reseat the card/reader if a reader appears without a disk. If several compatible cards are mounted, pass the exact path. |
| Unsupported model/firmware | Stop. Do not bypass checks or install firmware just to attempt recovery. Only the listed R13.3 build was investigated. |
| Existing hooks or update files | Preserve and inspect them. The installer refuses another `autoexec.ash`, debug trigger, legacy investigation script or firmware update file. Remove an older kit with its matching removal tool first. |
| macOS blocks the launcher | Open Terminal in the extracted release root and run `bash recovery-kit/prepare-macos.sh prepare`. This performs the same preparation. |
| No Bluetooth after startup | Wait the full minute, enter Setup phone, and check actual app access. Then power off and use the reader to inspect `RESULT.txt` in the newest `nb-bt-recovery-N` directory. Do not bypass checks or repeatedly reboot as a substitute for reading results. |
| Camera behaves unexpectedly | Power off, remove only this kit's owned startup files using the reader, safely eject, and boot normally. Reboot discards the temporary configuration. |

If there is **no result directory**, the startup hook did not run or preflight refused before any card writes. Refusals therefore create no claim or result directory. The short console acknowledgement confirms script entry only; refusal diagnostics go to stderr, which the RPC stdout acknowledgement does not expose. The conservative check can refuse when the known failure has scrolled out of the bounded console buffer, or if the diagnostic token is absent/changed. An entry line alone does not justify retrying or bypassing checks. A different underlying fault needs separate investigation.

## Privacy and support

Keep `nb-bt-recovery-*` folders, logs and XML private: they can contain camera/phone Bluetooth addresses, paired-device identifiers and pairing keys. Do not attach them unredacted to a public issue. Useful public reports include the camera model, firmware, host OS, kit version, exact installer error and sanitized result status.

The [technical notes](technical-notes.md) explain the demonstrated fault and evidence limits. [CLAUDE.md](../CLAUDE.md) instructs assistants to execute and verify the supported procedure without repeating the completed research. The [advanced repair guide](internal-storage-repair.md) is a separate destructive manual workflow, with its own prerequisites and limitations.

## Development checks

The release builder uses an explicit allowlist; private investigation files must stay excluded. Native launchers, tools and temporary payloads are in [`recovery-kit/`](../recovery-kit/); inactive advanced assets have a separate manifest in [`advanced/internal-drive-a/`](../advanced/internal-drive-a/).

From the repository root:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/build_release.py --check
python3 tools/build_release.py
```

On Windows, also run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/test_windows_installer.ps1
```

See the CI workflow for platform checks. The [passive console reader](../tools/capture_rtos.py) is Python 3/macOS-POSIX receive-only logging for the advanced workflow; native Windows capture is not validated. Host fixtures and pseudo-terminal tests do not establish physical radio/camera behavior.

Independent community tooling under the [MIT license](../LICENSE). Vendor firmware/executables and populated pairing configuration are excluded; the advanced ARM reader is built from this project's source.
