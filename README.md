# Nextbase 622GW Bluetooth repair

**Problem:** Internal Drive A cannot save Bluetooth configuration, preventing phone pairing.

**Fix:** Use the camera's own command to format Drive A and let stock Bluetooth recreate its configuration.

**Warning:** This erases internal Drive A files/settings. Verified on **one 622GW running R13.3**, with pairing retained across two full power-offs. A zero Bluetooth MAC alone does not establish this fault.

**[Download kit 0.2.0](https://github.com/DonLofto/Nextbase622GW/releases/download/v0.2.0/Nextbase622GW-recovery-0.2.0.zip)** · **[Checksum](https://github.com/DonLofto/Nextbase622GW/releases/download/v0.2.0/SHA256SUMS.txt)**

## Repair in five steps

Read the **[complete repair guide](docs/internal-storage-repair.md)** before copying anything to the card. It contains the compatibility checks, backups, console capture and harmless rehearsal required before formatting.

1. **Prepare.** Download and extract the kit, then complete the guide's preparation and checks.
2. **Run once.** Follow the supplied one-shot format procedure. Require `Drive 'A' format done.`; stop if it fails or the result is missing. Never re-arm the format claim.
3. **Pair.** Boot, stop recording, open **Connected App → Setup phone**, and connect in the Nextbase app. Confirm the camera or recordings are visible.
4. **Verify after reboot.** Fully power off, restart, and reconnect without pairing again, following the guide's persistence check.
5. **Clean up.** Remove the diagnostic hooks and console triggers, retain the consumed format claim, then verify another ordinary cold boot reconnects.

## Temporary access

The Mac/Windows double-click launchers provide a **temporary RAM workaround**, lost at reboot. They do not perform the repair above. [Temporary recovery instructions](docs/temporary-recovery.md).

## Details

[Research and test limits](docs/technical-notes.md) · [Agent instructions — CLAUDE.md](CLAUDE.md) · [MIT license](LICENSE)

Keep captures, configuration and pairing keys private. Long-term flash health and a working NAND restore method remain unproven.
