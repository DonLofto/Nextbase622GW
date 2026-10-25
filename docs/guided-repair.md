# Guided Drive A repair

Release **0.3.0** adds one macOS entry point: **`Repair Bluetooth.command`** in the extracted kit's root. It guides the persistent Drive A repair, handles the files and checks, and tells you when to move the card or reboot. The older launchers inside `recovery-kit/` still perform temporary RAM recovery only.

**Formatting erases internal Drive A files/settings.** The underlying repair worked on one **Nextbase 622GW / R13.3**; pairing survived two full power-offs, including a boot without diagnostic hooks. The new host wizard and its compatibility preflight are fixture-tested, **not camera-tested end to end**. Other models/builds, long-term flash health and a working NAND restore method are unproven. A zero MAC alone is not a diagnosis.

## Before starting

You need:

- A **Mac with Python 3.9 or newer** available as `python3`. The launcher uses the standard library; no Python packages or administrator access are required.
- A working **microSD reader**, the camera's card, and a USB **data** cable for the camera body's port. The mount's port is power only.
- Steady USB power, enough free space on the Mac for private captures, and time to follow several shutdown/card-transfer/boot prompts without interrupting the camera.
- Any files, recordings or settings you want preserved already saved elsewhere. **The launcher does not copy video recordings.** Its Drive A capture is not a full NAND backup and has no proven restore route.

This launcher supports **macOS only**. The [manual procedure](internal-storage-repair.md) remains available separately; native Windows passive capture is not validated. The [Windows temporary launcher](temporary-recovery.md) is a different operation.

## Download, verify and open

Download `Nextbase622GW-recovery-0.3.0.zip` and `SHA256SUMS.txt` from the [0.3.0 release](https://github.com/DonLofto/Nextbase622GW/releases/tag/v0.3.0) into the same folder. In Terminal, from that folder:

```sh
shasum -a 256 -c SHA256SUMS.txt
```

Require the ZIP's result to be `OK`; stop on any error or mismatch. Extract the **entire** ZIP onto the Mac, outside the card. Keep its folders together.

Stop recording, fully power the camera off, and connect its card through the reader. Disconnect other compatible camera cards. Open **`Repair Bluetooth.command`** from the extracted kit root and follow its Terminal prompts. Do not copy the launcher or the whole kit to the SD card.

If Finder will not open the launcher, open Terminal in the extracted kit root and run:

```sh
bash 'Repair Bluetooth.command'
```

If card detection is ambiguous, pass its verified mounted root explicitly:

```sh
bash 'Repair Bluetooth.command' --volume /Volumes/NEXTBASE
```

Use your actual card path. Do not guess a disk or serial device. The launcher keeps the Mac awake while running; keep the cable and camera power connected as instructed.

If multiple serial interfaces are present, disconnect unrelated devices or pass an already identified interface with `--port PATH`. List candidates without opening them using `python3 tools/capture_rtos.py --list`.

## What the prompts do

The tool verifies the kit and camera/card identity, refuses existing hooks/update files or previous claims, and checks the SD filesystem without repairing it. You must confirm the camera screen also says **622GW / R13.3**, that it is powered off during card handling, and that you have preserved what you need.

| Phase | What happens |
|---|---|
| **1. Prepare** | A read-only device preflight requires the exact runtime/vendor hashes, genuine A-backed storage and the documented configuration-creation failure. The frozen reader captures Drive A. The Mac verifies lengths, read coverage, statuses, hashes and provenance. Two further cold boots must show `NBFA01_DRYRUN`, then `NBFA01_SKIP`, with the empty claim retained. The SD filesystem is checked again. |
| **2. Run once** | After the warnings, approve exactly one format by typing **`FORMAT DRIVE A ONCE`**. Approval is durably consumed before the unchanged native format hook is staged. The tool requires one `NBFA02_BEGIN` and the exact vendor result **`Drive 'A' format done.`**. |
| **3. Pair** | A stock cold boot must show `NBFA02_SKIP` and Bluetooth startup, with no second format. Stop recording, open **Connected App → Setup phone → OK**, pair using the Nextbase app, and confirm it shows the camera or recordings. |
| **4. Verify after reboot** | The format hook is removed and a read-only observer is staged. After a full power-off, reconnect the app using its **existing pairing**, without Setup phone. The Mac checks saved configuration/pairing XML and genuine A-backed mounts, with no RAM overlay. |
| **5. Clean up** | Verified owned active hooks/scripts/tokens are removed; NBFA claims and results remain. After the final SD check and ejection, boot normally and confirm the existing app reconnects without pairing again. Choose **Power On** if the PC menu appears. |

For each diagnostic boot, the launcher ejects the card and waits for passive USB console output. Return it to the **powered-off** camera, connect the body USB data port to this Mac, and power on. The diagnostic trigger may skip the PC menu. When prompted to retrieve results, stop recording, shut down normally, and return the card to the reader. Do not try to retrieve diagnostic results through the camera's PC menu.

Console markers alone do not prove app access. Answer app questions from what you actually see. The final success report requires both existing-pairing reconnections and removal of active controls. The tool neither flashes firmware nor guesses Bluetooth XML, repairs the SD filesystem, resets the controller or automatically retries a format.

## If it stops or is interrupted

Read the reported error and keep the private session folder. A failed/missing check or result stops progression; do not bypass it or start a fresh session to retry.

**Ctrl+C stops the launcher, not an operation already running inside the camera.** A format has no proven completion deadline. If approval was consumed and completion is unknown, keep camera power connected, preserve the evidence and seek review; do not unplug merely to retry, delete the claim or assume success.

For safe removal of staged controls after a controlled shutdown:

1. With the camera fully off, connect the **same card** through the reader and reopen `Repair Bluetooth.command` on the **same Mac**.
2. An existing session offers its status and private evidence path. Press Return to quit, or type **`DISARM`** and confirm card handling to remove only unchanged, verified owned controls.
3. The tool retains claims, results, the inert session marker and private evidence, then ejects the card. Disarming is **not** a repair-success verdict.

Relaunching never resumes, re-arms or starts another format, even if the first attempt was interrupted before staging. Modified/unowned files or a missing/mismatched journal require review; they are not automatically deleted or adopted. Do not remove markers or create a new journal to get around a refusal.

## Evidence and privacy

Each attempt stores a private UUID session under **`~/Nextbase622GW Repairs/`**, including `state.json`, identity, SD checks, console captures and retrieved preflight/Drive A/persistence results. The card's inert **`nb-a-repair.json`** binds it to that session. Keep both and use the same Mac/card throughout; do not edit the journal or move/delete it during a repair.

These captures can contain camera/phone identifiers, configuration and pairing keys. Keep them out of public commits and issues. For support, share only sanitized model, firmware, tool version, error and session phase. The launcher never copies video recordings.

[Research, compatibility hashes and evidence limits](technical-notes.md) · [Full manual procedure](internal-storage-repair.md) · [Agent instructions](../CLAUDE.md)
