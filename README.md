# MisterScripts

Small tools for [MiSTer FPGA](https://github.com/MiSTer-devel/Main_MiSTer) (also works on MiSTer-based consoles such as the SuperStation One).

## mister_kbdmap.py: remap any keyboard key, no extra keyboard needed

MiSTer can remap keyboard keys from the OSD, but only by pressing the target key, so you
need a keyboard that actually has it. A typical case is the Amiga cores: **Right Amiga** is
the right Windows key, and many compact keyboards don't have one.

`mister_kbdmap.py` writes MiSTer's remap files directly. You can map any key to any key, swap
keys, edit or remove mappings, and optionally use **different mappings per core**. It can work
on the MiSTer over SSH from your PC, or run on the MiSTer itself.

Requirements: Python 3.7+ (MiSTer's own Python 3.9 works) and, for `--remote`, the OpenSSH
client. No extra Python packages.

### Quick start: Right Ctrl as Right Amiga

```sh
# 1. find your keyboard's VID:PID
./mister_kbdmap.py keyboards --remote 192.168.1.10
#   046d:404d  Logitech K400 Plus  -> kbd_046d_404d.map

# 2. make Right Ctrl act as the right Windows key (= Right Amiga in Minimig)
./mister_kbdmap.py map 046d:404d RCTRL=RGUI --remote 192.168.1.10
```

Load any core (or reboot) and it's active. Replace `192.168.1.10` with your MiSTer's IP.
The default login is `root` / `1`.

### Commands

| Command | What it does |
|---|---|
| `keys [FILTER]` | list key names and codes, e.g. `keys ctrl` |
| `keyboards` | list connected keyboards and the map file name for each |
| `map KBD SRC=DST ...` | add mappings, merged into the existing map (`--replace` starts empty) |
| `remove KBD KEY ...` | remove the mappings of these source keys (`--all` deletes the whole map) |
| `show [KBD\|FILE ...]` | decode maps (no argument: every map in the config folder) |
| `switcher` | install the per-core switcher on the MiSTer (`--start`, `--uninstall`) |
| `status` | running core, switcher state and the maps MiSTer is using now |
| `per-core-rgui KBD KEY` | Right Amiga in chosen cores via MiSTer's own INI option (see below) |

More examples:

```sh
./mister_kbdmap.py map 046d:404d CAPS=LCTRL LCTRL=CAPS --remote 192.168.1.10   # swap Caps Lock and Left Ctrl
./mister_kbdmap.py map 046d:404d SCRLK=F12 --remote 192.168.1.10               # Scroll Lock also opens the OSD
./mister_kbdmap.py remove 046d:404d CAPS LCTRL --remote 192.168.1.10           # undo the swap
./mister_kbdmap.py show --remote 192.168.1.10                                  # what's on the MiSTer
```

### Where it runs

- **On a PC with `--remote IP`:** reads and writes `/media/fat/config` on the MiSTer over SSH.
  Options: `--user` and `--password` (default `root` / `1`), the `KBDMAP_PASSWORD` environment
  variable, or `--remote user:password@ip[:port]`. The password is passed to `ssh` for you, so
  no extra tools are needed. Key-based SSH logins work too.
- **On the MiSTer itself** (copy it anywhere, run it over SSH with `python3 mister_kbdmap.py ...`):
  it detects the MiSTer and works on `/media/fat/config` directly.
- **On a PC without `--remote`:** works on files in the current folder (or `--dir`). Copy the
  results to `/media/fat/config/` yourself.

### Key names

Use the Linux key names (`RIGHTCTRL`, `RIGHTMETA`, `F12`, …, with or without `KEY_`), a numeric
code, or one of the short aliases: `LCTRL RCTRL LSHIFT RSHIFT LALT RALT/ALTGR`,
`LWIN/LGUI/LAMIGA`, `RWIN/RGUI/RAMIGA`, `APPS/MENUKEY` (the PC Menu key), `CAPS`, `SCRLK`,
`NUMLK`, `PRTSC`, `ISO` (the extra key next to Left Shift on ISO keyboards). Run
`./mister_kbdmap.py keys` for the full list. Typos get suggestions.

### Per-core mappings

MiSTer's map files apply to a keyboard model in **every** core. For different mappings in
different cores, the tool keeps per-core profiles, and a tiny background script copies the right
one into place whenever the core changes:

```sh
./mister_kbdmap.py map 046d:404d RCTRL=RGUI --core Minimig --remote 192.168.1.10
./mister_kbdmap.py map 046d:404d RCTRL=RGUI --core BigMig  --remote 192.168.1.10
./mister_kbdmap.py map 046d:404d CAPS=LCTRL --core default --remote 192.168.1.10   # optional: all other cores
./mister_kbdmap.py switcher --start --remote 192.168.1.10                           # once
./mister_kbdmap.py status --remote 192.168.1.10
```

- Profiles live in `/media/fat/config/kbdmap_cores/<Core>/kbd_VVVV_PPPP.map`.
- `<Core>` matches the same way `MiSTer.ini` sections do: either the core **file** name
  (`/tmp/RBFNAME`, e.g. `Minimig`, `BigMig`) or the name the core **reports**
  (`/tmp/CORENAME`, e.g. `Amiga`). The file name wins when both exist, so Minimig and BigMig can
  have different maps while an `Amiga` profile would cover both. Matching ignores capitalisation.
  `status` shows both names for the running core.
- `default` is used in every core without its own profile. Without a default, a managed keyboard
  gets no remap in other cores.
- The switcher (`/media/fat/linux/kbdmap_switcher.sh`) starts from `user-startup.sh`. It checks
  the core name 5 times a second, only writes when the map actually changes, and leaves
  keyboards without profiles alone. Keyboards that do have profiles are fully managed by it,
  so don't remap those in the OSD as well. Remove it with `switcher --uninstall` (profiles are kept).

#### Alternative without a background script (Right Amiga only)

`per-core-rgui 046d:404d RCTRL --core Minimig --core BigMig` maps the key to the PC Menu key in
every core and prints the `MiSTer.ini` lines (`key_menu_as_rgui=1` in `[Minimig]`/`[BigMig]`
sections) that turn Menu into Right Amiga in those cores only. In other cores that key then
acts as the PC Menu key.

### How it works: the file format

Taken from Main_MiSTer's `input.cpp` and checked against a map made with the OSD:

- `/media/fat/config/kbd_<vid>_<pid>.map`, lowercase hex, e.g. `kbd_046d_404d.map`. If you use
  `controller_unique_mapping` for that keyboard, the name gets an extra suffix; pass the full
  id, e.g. `046d_404d_1a2b3c4d`.
- Exactly **256 bytes**, one per Linux key code. `byte[source] = target`; `0` = not remapped.
  Only codes 1–255 can be remapped.
- Each key is translated **once**: `A=B` plus `B=C` gives A→B and B→C, not A→C. That's why a
  swap is simply two mappings.
- MiSTer reads the file on the first key press after a core starts (it restarts its main
  program on every core load). Changes take effect after loading a core, a reboot, or
  replugging the keyboard.

Notes:

- The tool warns when you remap `F12`, which opens the OSD.
- Wireless keyboards are identified by the keyboard, not the receiver. Use the id that
  `keyboards` shows.

### Background

Inspired by the forum thread
[Right Amiga on Pi (or other) keyboard without Menu key?](https://misterfpga.org/viewtopic.php?t=6592),
where the only solution was to borrow a keyboard with the right key for the OSD remap.
