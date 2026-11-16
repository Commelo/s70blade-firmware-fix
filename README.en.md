# S70 Blade Fix — unblocking ADATA's firmware updater

> **Video walkthrough of the case** (Brazilian Portuguese, with English subtitles):
> <https://www.youtube.com/watch?v=kgdAi8s8aTU>
>
> Versão em português deste guia: [README.md](README.md)

Some **XPG GAMMIX S70 BLADE** SSDs never show up in ADATA's official firmware updater. It is
not a faulty drive, not your chipset, not your machine: it is an **incomplete model whitelist
inside ADATA's own installer**. The drive identifies itself with its retail part number
(`AGAMMIXS70B-2T-CS`), and that string was simply never added to the list. The updater looks,
doesn't recognize it, and shows an empty list.

This repository documents the root cause, shows how to confirm it's your case, and provides a
script that adds your model to the list **without touching a single byte of ADATA's signed
firmware image**.

Outcome in the case that produced this work: a drive that spent **three years** unable to
update firmware went from `3.2.F.2A` (2021) to `3.2.F.66` in about thirty seconds — and that
also fixed a bug that made it **invisible under Linux**.

> The full write-up, including the dead ends, is in Portuguese in
> [DIAGNOSTICO.md](DIAGNOSTICO.md). This file is the complete practical guide in English.

---

## Does this apply to you?

There are **two distinct problems** here. The first is what this project fixes directly. The
second is a happy consequence that only applies to some people.

### Problem 1 — the updater doesn't see the drive

**Symptom:** you download the official firmware from ADATA's site, run it, and the drive list
is **empty**. It happens on any computer, with the drive alone or alongside others. ADATA SSD
Toolbox **does** see the drive and even recommends the update; only the updater is blind to it.

**Who's affected:** any drive whose reported Model Number isn't in the package's whitelist. In
`FWUpdate_32F66` the list is:

```
ModelName=XPG GAMMIX S70;XPG GAMMIX S70 BLADE;APSFG-1T-CSUS;APSFG-2T-CSUS;APSFG-512GCS;APSFG-1TCS;APSFG-2TCS
```

Note the asymmetry: the **PS5** line (`APSFG-*`) is covered **exhaustively by part number** —
all five SKUs. The **GAMMIX** line is covered **only by marketing name**. No `AGAMMIXS70B-*`
appears anywhere. Whoever wrote the list assumed every S70 Blade identifies by its commercial
name — part of the production run does not.

> **To check:** run `scripts/diagnostico_nvme.ps1` as Administrator (Windows). If your drive's
> `MN` is **not** in the `ModelName` list above, this is exactly your problem.

### Problem 2 — the drive is invisible under Linux

**Symptom:** the drive shows in BIOS and works under Windows, but never becomes `/dev/nvmeXn1`.
`dmesg` shows:

```
nvme nvme0: Invalid MNAN value 0
```

**Who's affected:** only drives on the old `3.2.F.xx` firmware family. This is **caused by the
old firmware** and fixed by updating — i.e. it's downstream of Problem 1, not separate.

### Decision table

| Your symptom | Does this help? |
|---|---|
| Official updater shows an empty list | **Yes** — this is exactly it |
| Invisible under Linux, `Invalid MNAN value 0` in dmesg | **Yes**, if you also can't update |
| Invisible under Linux but the updater works | You don't need this — just update normally |
| Drive doesn't appear in BIOS either | No. That's hardware |
| Drive appears but is slow / throwing errors | No. Different problem |
| Different brand or model | The **technique** may transfer, the file won't |

---

## What is actually broken

`FWUpdate_3.2.F.66.exe` is a Windows executable with a **ZIP archive embedded** in the middle
of it. The ZIP has three members:

| Member | Size | What it is |
|---|---|---|
| `Micron-B47R_0.fw` | 712,704 B | Firmware image for drives with Micron B47R NAND |
| `YMTC-X2-9060_1.fw` | 704,512 B | Firmware image for drives with YMTC X2-9060 NAND |
| `UpdateFWInfo.ini` | 1,816 B | Config file, UTF-16 |

`UpdateFWInfo.ini` is where the problem lives:

```ini
[UPDATEINFO]
TITLE=FFU_3.2.F.66
SOCID=5236
ModelName=XPG GAMMIX S70;XPG GAMMIX S70 BLADE;APSFG-1T-CSUS;...
FWVersion=3.2.F.P7;3.2.F.2A;3.2.F.2M;3.2.F.3C;3.2.F.46
iInternalFWVersionCheckPart=3
PowerCtrl=2
```

Two lists do the filtering: **`ModelName`** (which models may receive this firmware) and
**`FWVersion`** (which source versions may be upgraded from).

The detail that closes the case: the affected drive's version `3.2.F.2A` **is** in the
`FWVersion` list. ADATA clearly intended drives on that version to be updatable by this
package. Only the name was missing. It's an oversight, not a deliberate block.

### The fix

Add `AGAMMIXS70B-2T-CS` to the `ModelName` line. That's it.

The catch is that the INI is compressed inside a ZIP inside a PE. If the member grows, every
subsequent ZIP and PE offset shifts and the executable breaks. The approach used here keeps
the **compressed size identical**:

1. Recompress the modified INI with raw deflate.
2. Pad the remainder with zeros **after** the stream's `BFINAL` block. The inflater stops at
   `BFINAL` and ignores the rest — the zeros are inert.
3. Rewrite only the **CRC32** and **uncompressed size**, in the local header and the central
   directory.

Nothing shifts. The executable's size is unchanged. And critically, the two `.fw` images are
**never touched**: they remain ADATA's original signed binaries. The firmware that reaches the
SSD is the official firmware, byte for byte.

> **This is not modified firmware.** The firmware is ADATA's, unaltered. What's modified is the
> installer's model list — a text config file. The script refuses to write output if any byte
> inside the firmware images changes.

---

## The Linux bug, explained correctly

If you came here from `Invalid MNAN value 0`, read this. The diagnosis circulating online is
wrong, and it matters — it sends people looking in the wrong place.

Linux kernel, `drivers/nvme/host/multipath.c`, `nvme_mpath_init_identify()`:

```c
if (!multipath || !ctrl->subsys || !(ctrl->subsys->cmic & NVME_CTRL_CMIC_ANA))
        return 0;                                   /* NVME_CTRL_CMIC_ANA = 1 << 3 */
if (!ctrl->max_namespaces || ctrl->max_namespaces > le32_to_cpu(id->nn)) {
        dev_err(ctrl->device, "Invalid MNAN value %u\n", ctrl->max_namespaces);
        return -EINVAL;
}
```

The error message names MNAN, so everyone blames MNAN. But look at the first line: **only
drives with CMIC bit 3 set ever reach the MNAN check.**

Three NVMe SSDs measured in the same machine:

| Drive | Model Number | Firmware | CMIC | MNAN | Linux |
|---|---|---|---|---|---|
| S70 Blade 2 TB | `AGAMMIXS70B-2T-CS` | 3.2.F.2A | **0x4D** | 0 | **fails** |
| S70 Blade 4 TB | `XPG GAMMIX S70 BLADE` | 3.2.J.F0 | 0x00 | 0 | ok |
| X16 Plus 2 TB | `X16 Plus 2TB` | H231225a | 0x00 | 0 | ok |

**All three report MNAN = 0. Two work perfectly.** MNAN is not the cause. The discriminator is
**CMIC**.

`0x4D` = `0100 1101` → bits 0 (multi-port), 2 (SR-IOV virtual function), **3 (ANA)** and 6
(reserved). For a single-port consumer M.2 that's garbage — an uninitialized field in 2021
firmware. With bit 3 set, the kernel enters the ANA path (Asymmetric Namespace Access, an
enterprise storage feature), finds MNAN = 0, and rejects the whole device.

**Practical consequence:** the goal of updating is to **zero the CMIC**, not to "fix MNAN" —
MNAN will stay 0 and that's fine. Validate success by re-reading CMIC, not MNAN.

**Workaround** if you'd rather not flash: `nvme_core.multipath=0` on the kernel command line.
Zero performance cost on a single-port drive. Put it in `GRUB_CMDLINE_LINUX` (all entries),
**not** `GRUB_CMDLINE_LINUX_DEFAULT` — the latter skips recovery entries, and if your root
filesystem is on that disk you'd have no recovery path.

---

## Step by step

### 0. Back up. Seriously.

This is not boilerplate. You are flashing firmware. If it goes wrong the drive dies and there
is **no RMA** for a device flashed with a modified updater. ADATA has already bricked drives in
this family in an incident with firmware 3.2.9.1 — using their own unmodified updater.

If the drive you're updating is the **boot drive** (it was here), backup means a **full disk
image**, not a file copy. A failure takes the system down with it.

### 1. Find out what your drive reports

```powershell
# PowerShell as Administrator
powershell -ExecutionPolicy Bypass -File .\scripts\diagnostico_nvme.ps1
```

On Linux:

```bash
sudo nvme id-ctrl /dev/nvme0 | grep -E '^(mn|sn|fr|cmic|oacs|frmw|fwug|mnan)'
```

Note `MN`, `FR`, `CMIC`, `OACS`. You need:

- `MN` **not** in the `ModelName` list (otherwise your problem is something else);
- `FR` **in** the package's `FWVersion` list (otherwise it will refuse anyway);
- `OACS` with **bit 2** set (Firmware Download/Commit supported). `0x0007` and `0x0017` both
  qualify.

### 2. Download the official package

Go to ADATA's support page for the XPG GAMMIX S70 BLADE and download the firmware package. In
this case: `FWUpdate_32F66.zip`, containing `FWUpdate_3.2.F.66.exe`.

**Download it yourself, from the manufacturer.** This repository does not redistribute ADATA's
firmware or executable — and shouldn't.

### 3. Generate the executable with the corrected list

```bash
python scripts/patch_fwupdate.py \
    --exe "FWUpdate_3.2.F.66.exe" \
    --add "AGAMMIXS70B-2T-CS" \
    --out "FWUpdate_3.2.F.66_PATCHED.exe"
```

Replace `AGAMMIXS70B-2T-CS` with the **exact** `MN` string step 1 reported for your drive.

Needs only Python 3 and the standard library — no dependencies.

**No Python installed?** On Windows:

1. Download the installer from <https://www.python.org/downloads/> (any version 3.8 or newer).
2. On the installer's first screen, **tick "Add python.exe to PATH"** before clicking
   *Install Now*. Without it the `python` command is not found.
3. Close and reopen PowerShell, then check:

   ```powershell
   python --version
   ```

   It should print something like `Python 3.12.x`. If the Microsoft Store opens instead, step 2
   was skipped: run the installer again and tick the option.

One-line alternative via the Windows package manager: `winget install Python.Python.3.12`.
If you already have Blender, its bundled Python works too (`4.x/python/bin/python.exe`).

**In PowerShell, write the command on a single line.** The trailing `\` used in the examples
above only works in bash-like shells:

```powershell
python scripts/patch_fwupdate.py --exe "FWUpdate_3.2.F.66.exe" --add "AGAMMIXS70B-2T-CS" --out "FWUpdate_3.2.F.66_PATCHED.exe"
```

Run the commands from inside the repository folder, with the downloaded
`FWUpdate_3.2.F.66.exe` in the same folder (or pass its full path to `--exe`).

The script prints the list before and after, warns if it had to drop any entry to fit the
compressed size, and **aborts** if any byte of the firmware images would change.

> **Reproducibility.** Run with Python 3.10 against the original `FWUpdate_3.2.F.66.exe`
> (SHA-256 `0bad90b3f4852f4764f9492c67e40f5ef22d9f2ca99d3d3435c5e7b0827b4260`), the output has
> SHA-256 `ae5bd4041c3bf3053fdf5faf33450b4049a60ee68e7109541e78ff77bda1acd9` — bit for bit the
> same file used in the flash documented here. If yours matches, you have exactly the verified
> executable. If it doesn't, don't panic: different zlib versions can emit different compressed
> bytes. What decides is the step 4 verdict, not the hash.

### 4. Verify before running anything

```bash
python scripts/verifica_patch.py \
    --original "FWUpdate_3.2.F.66.exe" \
    --patched  "FWUpdate_3.2.F.66_PATCHED.exe" \
    --esperar  "AGAMMIXS70B-2T-CS"
```

This script **writes nothing**. It compares the SHA-256 of each `.fw` image between the two
executables and only returns `APROVADO` (approved) if:

- the `.fw` images are **identical** to the original;
- ZIP CRCs are consistent;
- the new model is in the whitelist;
- the executable size is preserved.

If it says `REPROVADO`, stop. Do not use it.

### 5. Prepare the machine

- Disconnect or offline any drive you **don't** want to update. The updater lists everything
  that passes the filter, and misclicking is easy.
- Close everything. No downloads, torrents, or builds running.
- **Laptop: plug it in.** Desktop: this is what the UPS is for.
- With two drives of the same model, identify by **current firmware version**, not by name —
  enumeration gets confusing with identical drives.

### 6. Run as Administrator

Run the `_PATCHED.exe`. The drive should now appear. Check the serial number on screen before
confirming. Accept the warning, wait, reboot when prompted. The flash itself takes seconds.

### 7. Verify the result

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verificar_apos_flash.ps1
```

You want two things: `FR` changed, and `CMIC` became `0x00`. The script tells you explicitly
whether you can now drop `nvme_core.multipath=0` from your boot line.

---

## Warnings

**Read before deciding.**

- **Firmware updates can brick an SSD.** True of the official updater too. The risk is not
  zero and never becomes zero.
- **You forfeit any RMA claim.** A drive bricked with a modified updater will not be replaced
  under warranty. Accept that consciously.
- **Full backup first. No exceptions.**
- **This is not ADATA software and has no affiliation with ADATA.** It is independent
  documentation of a defect in their product.
- **Do not use on a model other than your own.** In a manufacturer whitelist, the model string
  is a proxy for factory configuration: NAND binning, capacity map, controller stepping.
  Sometimes it's protecting you from a legitimate brick. Bypassing it is safe **only** when you
  have independent evidence that the firmware is right for your hardware.

In the documented case, that evidence was five converging facts:

1. `AGAMMIXS70B-2T-CS` is the **official retail part number** of the S70 Blade 2 TB — listed on
   Amazon, Newegg, PCPartPicker. Not a stray factory string.
2. The drive's NAND (Micron B47R) has an image **present in the package**.
3. The package's `SOCID=5236` matches the controller.
4. The PCI ID (`VEN_1CC1&DEV_5370`) is **identical** to the 4 TB S70 Blade in the same machine,
   which the whitelist accepts — same controller platform.
5. The source version `3.2.F.2A` **is** in the package's own `FWVersion` list.

If you can't assemble a comparable list for your case, **don't do it**.

---

## Verified vs. not verified

Being explicit about the evidence base, because it matters when the cost of being wrong is an SSD.

**Empirically verified on a real drive:**

- The executable with the corrected list **does** make the updater see the drive.
- The flash completed and Windows booted normally — on the boot drive itself.
- `FR` went from `3.2.F.2A` to `3.2.F.66`, confirmed by reading Identify Controller directly.
- `CMIC` went from `0x4D` to `0x00`. **This fixes the Linux bug.**
- The `.fw` images in the modified executable have SHA-256 identical to the original.

**Not verified:**

- **Sample size of one.** One drive, one machine, one firmware package. It worked. That is not
  a statistic.
- **Removing `nvme_core.multipath=0` was later tested on a real boot and it worked**
  (2026-11-16): the drive shows up on Linux without the parameter. What is still missing is the
  record — the `lsblk` and `/proc/cmdline` output from that boot is not archived under `dados/`,
  so for now this is the author's report, not a checkable log.
- **The Model Number does not change with the update.** Still `AGAMMIXS70B-2T-CS`. MN lives in
  the factory-written mass production config area, separate from firmware code. Consequence:
  **future ADATA updaters will remain blind to this drive**, and the same procedure will be
  needed again.
- **`ActiveSlot` still reports 0**, which is not a valid value per the NVMe spec (should be
  1–7). This persists on 3.2.F.66. Apparently cosmetic.
- **The `3.2.J.xx` family was not tested** on this drive. The 4 TB runs `3.2.J.F0` with
  CMIC = 0x00, so it's presumably fine, but there's no tested `F.66` → `J.xx` path.

**Investigated and ruled out:**

- **RAID / VMD / Intel RST** — all controllers appear as "Standard NVM Express Controller".
  Pure NVMe mode. Not it.
- **MNAN blocking Vendor Specific commands** — unfounded. MNAN is a read-only informational
  field (bytes 543:540), and `OACS` proves firmware commands are accepted. This wrong
  hypothesis is what led to hours decompiling the executable — the wrong layer entirely.
- **Hand-editing CMIC or MNAN in a firmware image** — infeasible. InnoGrit has AES-256 keys
  fused in silicon and validates the image signature.
- **MPTool (production tool)** — total data loss, high brick risk, no RMA. Unnecessary.

---

## Files

```
s70blade-fix/
├── README.md                      Portuguese (primary)
├── README.en.md                   this file
├── DIAGNOSTICO.md                 the full investigation (Portuguese)
├── LICENSE                        public domain (CC0)
├── scripts/
│   ├── diagnostico_nvme.ps1       reads MN/FR/CMIC/OACS/FRMW of all NVMe drives (Windows)
│   ├── extrair_pacote.py          extracts the ZIP embedded in the installer (.fw + .ini)
│   ├── patch_fwupdate.py          adds models to the installer's whitelist
│   ├── verifica_patch.py          read-only verification before use
│   └── verificar_apos_flash.ps1   confirms FR and CMIC after flashing
└── dados/
    ├── whitelist_original.txt     the original whitelist, transcribed
    └── verificacao_pos_flash.txt  the real output confirming the result
```

Script output is in Portuguese. The logic is language-independent and the README explains what
each field means.

No ADATA firmware, executable, or copyrighted material is redistributed here. Download the
package from the manufacturer.

---

## License and liability

Scripts in this repository are public domain (CC0) — use them however you like.

**No warranty of any kind.** You are responsible for what you do to your hardware. If your SSD
bricks, that's on you. Read the warnings, take a backup, and decide with your eyes open.

This project has no affiliation with ADATA, XPG, or InnoGrit.
