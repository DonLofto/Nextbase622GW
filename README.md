# Nextbase 622GW Bluetooth repair

**Problem:** Internal Drive A cannot save Bluetooth configuration, preventing phone pairing.

**Fix:** Use the camera's own command to format Drive A and let stock Bluetooth recreate its configuration.

**Warning:** This erases internal Drive A files/settings. The repair worked on **one 622GW running R13.3**, with pairing retained across two full power-offs. The new guided launcher is fixture-tested; it has **not** been run end to end on a camera. A zero Bluetooth MAC alone does not establish this fault.

## Download and open

| Computer | Download | Open after extracting the **entire ZIP** |
|---|---|---|
| **Windows 10/11 x64** | **[Windows kit 0.5.0](https://github.com/DonLofto/Nextbase622GW/releases/download/v0.5.0/Nextbase622GW-Windows-0.5.0.zip)** | **`Nextbase622GW-Repair.exe`**; accept the administrator prompt |
| **Mac** | **[Mac/source kit 0.5.0](https://github.com/DonLofto/Nextbase622GW/releases/download/v0.5.0/Nextbase622GW-recovery-0.5.0.zip)** | **`Repair Bluetooth.command`**; requires Python 3.9+ |

**Windows includes Python.** Keep the EXE and its `_internal` folder together; no installer or Python setup is needed. Verify your download using the **[checksums](https://github.com/DonLofto/Nextbase622GW/releases/download/v0.5.0/SHA256SUMS.txt)**. The EXE is unsigned. [Verification and help](docs/guided-repair.md).

You need a microSD reader, a USB data cable connected to the camera's **body** port, and steady power. Both platforms use the same checks and format confirmation.

The launcher guides you through:

1. **Prepare:** check compatibility and the actual fault, capture Drive A, and rehearse the one-shot guard.
2. **Run once:** explicitly approve one internal-A format. Never re-arm or retry it.
3. **Pair:** connect in the Nextbase app and confirm camera/recordings access.
4. **Verify after reboot:** reconnect using the existing pairing.
5. **Clean up:** remove active hooks, retain the consumed claim, and confirm an ordinary cold boot reconnects.

If a check fails, stop. Relaunching offers inspection or removal of verified owned controls; it never resumes the repair.

## Other paths and details

- [Temporary RAM recovery](docs/temporary-recovery.md): existing Mac/Windows launchers; lost at reboot.
- [Manual repair procedure](docs/internal-storage-repair.md) · [Research and limits](docs/technical-notes.md) · [Agent instructions](CLAUDE.md) · [MIT license](LICENSE)

Keep captures and pairing keys private. Long-term flash health and a working NAND restore method remain unproven.
