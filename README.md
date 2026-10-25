# Nextbase 622GW Bluetooth recovery

**[Download recovery kit 0.2.0](https://github.com/DonLofto/Nextbase622GW/releases/download/v0.2.0/Nextbase622GW-recovery-0.2.0.zip)** · **[SHA256 checksums](https://github.com/DonLofto/Nextbase622GW/releases/download/v0.2.0/SHA256SUMS.txt)**

For the **Nextbase 622GW / R13.3** fault where Bluetooth cannot create `/tmp/FL0/bt_config.xml`. The affected camera showed a zero Bluetooth MAC, a name ending in `000`, and failed phone pairing. **A zero MAC alone does not establish this fault.** Other models, firmware and Bluetooth faults are outside the tested scope; the temporary kit checks compatibility before acting.

## Choose a recovery

| Route | What it does |
|---|---|
| **Temporary recovery — start here** | The Mac/Windows launcher uses RAM for configuration. It is lost at reboot; re-arm for another session. No internal format. |
| [Advanced internal-storage repair](docs/internal-storage-repair.md) | A separate manual procedure that **erases internal Drive A files/settings**. Requires verified captures/backups, healthy SD storage, passive console evidence, a harmless two-boot rehearsal and explicit approval for one format attempt. |

The original RAM operation restored app access on one camera. **The guarded temporary package has not been boot-tested end to end on a camera.** The advanced repair retained pairing across two post-pairing cold boots on that unit, including an ordinary boot after all hooks were removed. The original cause, long-term NAND health and a working NAND restore method remain unproven. [Evidence and limits](docs/technical-notes.md#validation).

## Temporary recovery in five steps

You need a Mac or Windows PC, the camera's microSD card, preferably a reader, and steady power. Save any recordings you need.

1. **Download the ZIP above, verify its checksum, and extract it completely** onto your computer. Keep the folders together; do not run files inside the ZIP. [Checksum instructions](docs/temporary-recovery.md#verify-the-download).
2. **Stop recording and power the camera off.** Put its card in a reader. Alternatively, use a data cable at the camera body's mini-USB port and choose **Firmware Update** for writable card access. The mount's USB port supplies power only. Do not add firmware files.
3. Open **`recovery-kit/Recover Bluetooth.command`** on macOS or **`recovery-kit/Recover Bluetooth.cmd`** on Windows. Follow the tool's messages. It verifies and copies the files; stop if it refuses compatibility or existing files.
4. **Safely eject.** Return the card to the powered-off camera, or power off/unplug the camera if using USB storage. Reconnect its **body USB data port** to the computer, turn it on, and **wait one minute**. The diagnostic trigger may skip the PC menu.
5. **Stop recording → cog → Connected App → Setup phone → OK.** Pair in the Nextbase app and confirm it shows the camera or recordings. Leave the camera powered for this session.

`ATTEMPT_COMPLETE` means the script finished its attempt; actual app access proves success. Reboot discards the RAM configuration and can lose pairing.

## Help and details

- [Temporary recovery guide](docs/temporary-recovery.md): cleanup, re-arming, troubleshooting and developer checks.
- [Technical notes](docs/technical-notes.md): diagnosis, operation and compatibility hashes.
- [CLAUDE.md](CLAUDE.md): agent execution instructions; the supported procedure is already researched.

Keep logs, XML, pairing keys and result folders private. For public support, provide model, firmware, host OS, tool error and sanitized status only.

Independent community tooling under the [MIT license](LICENSE). No vendor firmware, vendor executables or populated pairing configuration is distributed.
