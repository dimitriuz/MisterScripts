#!/usr/bin/env python3
"""Create and edit MiSTer keyboard remap files (config/kbd_VVVV_PPPP.map) for any key,
without needing a keyboard that has the target key. Works on a PC, on the MiSTer itself,
or from a PC directly on the MiSTer over SSH (--remote).

File format (from Main_MiSTer input.cpp, verified against a real file):
  - exactly 256 bytes, one per Linux key code 0..255
  - byte[source_key] = target_key; 0 means "not remapped"
  - each key is translated once (A=B plus B=C gives A->B and B->C, not A->C),
    so swapping two keys is simply two mappings: CAPS=LCTRL LCTRL=CAPS
  - name: kbd_<vid>_<pid>.map in /media/fat/config, lowercase hex, e.g. kbd_046d_404d.map
  - applies to that one keyboard model, in ALL cores (the name has no core in it)
  - read when the keyboard is first used after a core starts (or after a reboot/replug)

Commands:
  keys [FILTER]                        list key names and codes
  keyboards [FILE]                     list connected keyboards and their VID:PID
  map KBD SRC=DST [SRC=DST ...]        add mappings (merged into the existing file, if any)
  remove KBD KEY [KEY ...] | --all     remove mappings of the given source keys, or the whole file
  show [KBD|FILE ...]                  decode map files (no argument: all maps in the folder)
  switcher                             per-core maps: install (--remote/on MiSTer) or write the script
  status                               running core names, switcher state and live maps on the MiSTer
  per-core-rgui KBD KEY                make KEY act as Right GUI/Right Amiga only in chosen cores,
                                       via MiSTer's own key_menu_as_rgui option (no extra script)

Common options (put them after the command):
  --remote HOST        work on the MiSTer at HOST over SSH; HOST may be [user[:password]@]ip[:port]
  --user / --password  SSH login, default root / 1 (or set KBDMAP_PASSWORD)
  --dir DIR            config folder; default /media/fat/config on the MiSTer or with --remote,
                       otherwise the current folder
  --core NAME          (map/remove/show) per-core map in kbdmap_cores/NAME/, 'default' = all other cores;
                       NAME is the core file name (Minimig, BigMig) or the name the core reports
                       (Amiga), like MiSTer.ini sections; 'status' shows both for the running core.
                       Per-core maps need the switcher installed on the MiSTer.

Examples:
  ./mister_kbdmap.py keyboards --remote 192.168.1.10
  ./mister_kbdmap.py map 046d:404d RCTRL=RGUI --remote 192.168.1.10            # Right Ctrl = right Win
  ./mister_kbdmap.py map 046d:404d CAPS=LCTRL LCTRL=CAPS --remote 192.168.1.10  # swap two keys
  ./mister_kbdmap.py remove 046d:404d CAPS LCTRL --remote 192.168.1.10         # undo the swap
  ./mister_kbdmap.py map 046d:404d RCTRL=RGUI --core Minimig --remote 192.168.1.10
  ./mister_kbdmap.py switcher --remote 192.168.1.10                            # makes --core maps work
  ./mister_kbdmap.py show --remote 192.168.1.10                                # everything on the MiSTer
"""
import argparse
import difflib
import glob
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

# Linux input key codes 1..255 (from linux/input-event-codes.h). First name is the primary one.
KEY_CODES = {
    1: ['ESC'],
    2: ['1'],
    3: ['2'],
    4: ['3'],
    5: ['4'],
    6: ['5'],
    7: ['6'],
    8: ['7'],
    9: ['8'],
    10: ['9'],
    11: ['0'],
    12: ['MINUS'],
    13: ['EQUAL'],
    14: ['BACKSPACE'],
    15: ['TAB'],
    16: ['Q'],
    17: ['W'],
    18: ['E'],
    19: ['R'],
    20: ['T'],
    21: ['Y'],
    22: ['U'],
    23: ['I'],
    24: ['O'],
    25: ['P'],
    26: ['LEFTBRACE'],
    27: ['RIGHTBRACE'],
    28: ['ENTER'],
    29: ['LEFTCTRL'],
    30: ['A'],
    31: ['S'],
    32: ['D'],
    33: ['F'],
    34: ['G'],
    35: ['H'],
    36: ['J'],
    37: ['K'],
    38: ['L'],
    39: ['SEMICOLON'],
    40: ['APOSTROPHE'],
    41: ['GRAVE'],
    42: ['LEFTSHIFT'],
    43: ['BACKSLASH'],
    44: ['Z'],
    45: ['X'],
    46: ['C'],
    47: ['V'],
    48: ['B'],
    49: ['N'],
    50: ['M'],
    51: ['COMMA'],
    52: ['DOT'],
    53: ['SLASH'],
    54: ['RIGHTSHIFT'],
    55: ['KPASTERISK'],
    56: ['LEFTALT'],
    57: ['SPACE'],
    58: ['CAPSLOCK'],
    59: ['F1'],
    60: ['F2'],
    61: ['F3'],
    62: ['F4'],
    63: ['F5'],
    64: ['F6'],
    65: ['F7'],
    66: ['F8'],
    67: ['F9'],
    68: ['F10'],
    69: ['NUMLOCK'],
    70: ['SCROLLLOCK'],
    71: ['KP7'],
    72: ['KP8'],
    73: ['KP9'],
    74: ['KPMINUS'],
    75: ['KP4'],
    76: ['KP5'],
    77: ['KP6'],
    78: ['KPPLUS'],
    79: ['KP1'],
    80: ['KP2'],
    81: ['KP3'],
    82: ['KP0'],
    83: ['KPDOT'],
    85: ['ZENKAKUHANKAKU'],
    86: ['102ND'],
    87: ['F11'],
    88: ['F12'],
    89: ['RO'],
    90: ['KATAKANA'],
    91: ['HIRAGANA'],
    92: ['HENKAN'],
    93: ['KATAKANAHIRAGANA'],
    94: ['MUHENKAN'],
    95: ['KPJPCOMMA'],
    96: ['KPENTER'],
    97: ['RIGHTCTRL'],
    98: ['KPSLASH'],
    99: ['SYSRQ'],
    100: ['RIGHTALT'],
    101: ['LINEFEED'],
    102: ['HOME'],
    103: ['UP'],
    104: ['PAGEUP'],
    105: ['LEFT'],
    106: ['RIGHT'],
    107: ['END'],
    108: ['DOWN'],
    109: ['PAGEDOWN'],
    110: ['INSERT'],
    111: ['DELETE'],
    112: ['MACRO'],
    113: ['MUTE'],
    114: ['VOLUMEDOWN'],
    115: ['VOLUMEUP'],
    116: ['POWER'],
    117: ['KPEQUAL'],
    118: ['KPPLUSMINUS'],
    119: ['PAUSE'],
    120: ['SCALE'],
    121: ['KPCOMMA'],
    122: ['HANGEUL'],
    123: ['HANJA'],
    124: ['YEN'],
    125: ['LEFTMETA'],
    126: ['RIGHTMETA'],
    127: ['COMPOSE'],
    128: ['STOP'],
    129: ['AGAIN'],
    130: ['PROPS'],
    131: ['UNDO'],
    132: ['FRONT'],
    133: ['COPY'],
    134: ['OPEN'],
    135: ['PASTE'],
    136: ['FIND'],
    137: ['CUT'],
    138: ['HELP'],
    139: ['MENU'],
    140: ['CALC'],
    141: ['SETUP'],
    142: ['SLEEP'],
    143: ['WAKEUP'],
    144: ['FILE'],
    145: ['SENDFILE'],
    146: ['DELETEFILE'],
    147: ['XFER'],
    148: ['PROG1'],
    149: ['PROG2'],
    150: ['WWW'],
    151: ['MSDOS'],
    152: ['COFFEE'],
    153: ['ROTATE_DISPLAY'],
    154: ['CYCLEWINDOWS'],
    155: ['MAIL'],
    156: ['BOOKMARKS'],
    157: ['COMPUTER'],
    158: ['BACK'],
    159: ['FORWARD'],
    160: ['CLOSECD'],
    161: ['EJECTCD'],
    162: ['EJECTCLOSECD'],
    163: ['NEXTSONG'],
    164: ['PLAYPAUSE'],
    165: ['PREVIOUSSONG'],
    166: ['STOPCD'],
    167: ['RECORD'],
    168: ['REWIND'],
    169: ['PHONE'],
    170: ['ISO'],
    171: ['CONFIG'],
    172: ['HOMEPAGE'],
    173: ['REFRESH'],
    174: ['EXIT'],
    175: ['MOVE'],
    176: ['EDIT'],
    177: ['SCROLLUP'],
    178: ['SCROLLDOWN'],
    179: ['KPLEFTPAREN'],
    180: ['KPRIGHTPAREN'],
    181: ['NEW'],
    182: ['REDO'],
    183: ['F13'],
    184: ['F14'],
    185: ['F15'],
    186: ['F16'],
    187: ['F17'],
    188: ['F18'],
    189: ['F19'],
    190: ['F20'],
    191: ['F21'],
    192: ['F22'],
    193: ['F23'],
    194: ['F24'],
    200: ['PLAYCD'],
    201: ['PAUSECD'],
    202: ['PROG3'],
    203: ['PROG4'],
    204: ['ALL_APPLICATIONS'],
    205: ['SUSPEND'],
    206: ['CLOSE'],
    207: ['PLAY'],
    208: ['FASTFORWARD'],
    209: ['BASSBOOST'],
    210: ['PRINT'],
    211: ['HP'],
    212: ['CAMERA'],
    213: ['SOUND'],
    214: ['QUESTION'],
    215: ['EMAIL'],
    216: ['CHAT'],
    217: ['SEARCH'],
    218: ['CONNECT'],
    219: ['FINANCE'],
    220: ['SPORT'],
    221: ['SHOP'],
    222: ['ALTERASE'],
    223: ['CANCEL'],
    224: ['BRIGHTNESSDOWN'],
    225: ['BRIGHTNESSUP'],
    226: ['MEDIA'],
    227: ['SWITCHVIDEOMODE'],
    228: ['KBDILLUMTOGGLE'],
    229: ['KBDILLUMDOWN'],
    230: ['KBDILLUMUP'],
    231: ['SEND'],
    232: ['REPLY'],
    233: ['FORWARDMAIL'],
    234: ['SAVE'],
    235: ['DOCUMENTS'],
    236: ['BATTERY'],
    237: ['BLUETOOTH'],
    238: ['WLAN'],
    239: ['UWB'],
    240: ['UNKNOWN'],
    241: ['VIDEO_NEXT'],
    242: ['VIDEO_PREV'],
    243: ['BRIGHTNESS_CYCLE'],
    244: ['BRIGHTNESS_AUTO'],
    245: ['DISPLAY_OFF'],
    246: ['WWAN'],
    247: ['RFKILL'],
    248: ['MICMUTE'],
}

MAP_SIZE = 256
MISTER_CONFIG = "/media/fat/config"
MISTER_LINUX = "/media/fat/linux"
PROFILE_DIR = "kbdmap_cores"      # per-core maps: kbdmap_cores/<CoreName>/kbd_VVVV_PPPP.map
DEFAULT_PROFILE = "default"        # used for every core that has no profile of its own
SWITCHER_NAME = "kbdmap_switcher.sh"
STARTUP_MARK = "# kbdmap_switcher"

# Friendly aliases for common keys (all case-insensitive, "KEY_" prefix optional).
ALIASES = {
    "LCTRL": 29, "RCTRL": 97, "LSHIFT": 42, "RSHIFT": 54, "LALT": 56, "RALT": 100, "ALTGR": 100,
    "LWIN": 125, "LGUI": 125, "LMETA": 125, "LSUPER": 125, "LAMIGA": 125,
    "RWIN": 126, "RGUI": 126, "RMETA": 126, "RSUPER": 126, "RAMIGA": 126,
    "APPS": 127, "MENUKEY": 127, "CONTEXT": 127,   # the PC "Menu"/application key = KEY_COMPOSE
    "PRINTSCREEN": 99, "PRTSC": 99, "SCRLK": 70, "CAPS": 58, "NUMLK": 69,
    "ISO": 86,                                       # extra key next to left Shift on ISO keyboards
}

NAME_TO_CODE = {}
for _code, _names in KEY_CODES.items():
    for _n in _names:
        NAME_TO_CODE.setdefault(_n, _code)
NAME_TO_CODE.update(ALIASES)

# Keys MiSTer itself uses; remapping them away can make the OSD hard to reach.
MISTER_KEYS = {88: "F12 opens the MiSTer OSD", 139: "MENU opens the MiSTer OSD"}

SWITCHER_SCRIPT = r'''#!/bin/sh
# kbdmap_switcher.sh - per-core keyboard remaps for MiSTer (generated by mister_kbdmap.py)
#
# Profiles:  /media/fat/config/kbdmap_cores/<CoreName>/kbd_VVVV_PPPP.map
#            /media/fat/config/kbdmap_cores/default/kbd_VVVV_PPPP.map  (all other cores, optional)
# <CoreName> matches like MiSTer.ini sections do: the core file name (/tmp/RBFNAME, e.g.
# Minimig, BigMig) or the name the core reports (/tmp/CORENAME, e.g. Amiga); the file
# name wins when both match. On every core change the matching map is copied to
# /media/fat/config/kbd_VVVV_PPPP.map, where MiSTer reads it on the first key press.
# Keyboards with no profile file at all are left untouched. For keyboards that do have
# profiles, the live file is removed in cores without a profile and without a default.

CFG="${KBDMAP_CFG:-/media/fat/config}"
CORENAME_FILE="${KBDMAP_CORENAME:-/tmp/CORENAME}"
RBFNAME_FILE="${KBDMAP_RBFNAME:-/tmp/RBFNAME}"
PIDFILE="${KBDMAP_PIDFILE:-/tmp/kbdmap_switcher.pid}"
PROFILES="$CFG/kbdmap_cores"
POLL="${KBDMAP_POLL:-0.2}"

if [ -z "$KBDMAP_ONCE" ]; then
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then exit 0; fi
  echo $$ > "$PIDFILE"
fi

lower() { printf '%s' "$1" | tr 'A-Z' 'a-z'; }

apply() {   # $1 = core file name (RBFNAME), $2 = core's own name (CORENAME)
  rbf_lc=$(lower "$1")
  core_lc=$(lower "$2")
  dir=""
  for d in "$PROFILES"/*/; do
    [ -d "$d" ] || continue
    n=$(basename "$d")
    [ "$n" = "default" ] && continue
    n_lc=$(lower "$n")
    if [ -n "$rbf_lc" ] && [ "$n_lc" = "$rbf_lc" ]; then dir="${d%/}"; break; fi
    [ -n "$core_lc" ] && [ "$n_lc" = "$core_lc" ] && dir="${d%/}"
  done
  for f in "$PROFILES"/*/kbd_*.map; do
    [ -f "$f" ] && basename "$f"
  done | sort -u | while read -r name; do
    src=""
    [ -n "$dir" ] && [ -f "$dir/$name" ] && src="$dir/$name"
    [ -z "$src" ] && [ -f "$PROFILES/default/$name" ] && src="$PROFILES/default/$name"
    if [ -n "$src" ]; then
      cmp -s "$src" "$CFG/$name" || cp "$src" "$CFG/$name"
    else
      rm -f "$CFG/$name"
    fi
  done
}

last="__none__"
while :; do
  core=""
  rbf=""
  [ -r "$CORENAME_FILE" ] && read -r core < "$CORENAME_FILE"
  [ -r "$RBFNAME_FILE" ] && read -r rbf < "$RBFNAME_FILE"
  if [ "$rbf|$core" != "$last" ]; then
    apply "$rbf" "$core"
    last="$rbf|$core"
    [ -n "$KBDMAP_ONCE" ] && exit 0
  fi
  sleep "$POLL"
done
'''


# ---------------------------------------------------------------- keys and ids

def key_name(code):
    return KEY_CODES.get(code, ["CODE_%d" % code])[0]


def parse_key(text):
    t = text.strip()
    if re.fullmatch(r"\d+", t):
        code = int(t)
    else:
        u = t.upper()
        if u.startswith("KEY_"):
            u = u[4:]
        if u not in NAME_TO_CODE:
            close = difflib.get_close_matches(u, NAME_TO_CODE, n=6, cutoff=0.6)
            close += sorted(n for n in NAME_TO_CODE if len(u) > 1 and u in n and n not in close)[:6]
            hint = " (did you mean: %s?)" % ", ".join(close) if close else ""
            raise ValueError("unknown key '%s'%s; run 'keys' to list names" % (text, hint))
        code = NAME_TO_CODE[u]
    if not 1 <= code <= 255:
        raise ValueError("key code %d out of range: MiSTer only remaps codes 1..255" % code)
    return code


def parse_kbd_id(text):
    """Accept 046d:404d, 046D_404D, 0x046d:0x404d, or a full MiSTer id like 046d_404d_1a2b3c4d."""
    t = text.strip().lower().replace("0x", "")
    m = re.fullmatch(r"([0-9a-f]{1,4})[:_]([0-9a-f]{1,4})((?:_[0-9a-z_.-]+)?)", t)
    if not m:
        raise ValueError("bad keyboard id '%s', expected VID:PID like 046d:404d" % text)
    return "%04x_%04x%s" % (int(m.group(1), 16), int(m.group(2), 16), m.group(3))


def parse_core(text):
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", text):
        raise ValueError("bad core name '%s' (use the name in /tmp/CORENAME, e.g. Minimig)" % text)
    return text


def map_relpath(kbd_id, core):
    fname = "kbd_%s.map" % kbd_id
    return "%s/%s/%s" % (PROFILE_DIR, core, fname) if core else fname


def describe(table):
    rows = [(src, dst) for src, dst in enumerate(table) if dst]
    if not rows:
        return "  (no keys remapped)"
    return "\n".join("  %14s (%3d)  ->  %s (%d)" % (key_name(s), s, key_name(d), d) for s, d in rows)


def check_map(data, where):
    if len(data) != MAP_SIZE:
        raise ValueError("%s: %d bytes, a MiSTer kbd map must be exactly %d" % (where, len(data), MAP_SIZE))
    return bytearray(data)


def warn_mister_keys(table):
    for src, dst in enumerate(table):
        if dst and src in MISTER_KEYS:
            print("warning: %s is remapped; %s" % (key_name(src), MISTER_KEYS[src]), file=sys.stderr)


def on_mister():
    return os.path.isdir(MISTER_CONFIG) and os.path.exists("/media/fat/MiSTer")


# ---------------------------------------------------------------- storage: local or over SSH

class LocalStore:
    remote = False

    def __init__(self, config_dir):
        self.config = config_dir

    def label(self, path):
        return path

    def read(self, path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def write(self, path, data):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)

    def delete(self, path):
        try:
            os.remove(path)
        except FileNotFoundError:
            return False
        d = os.path.dirname(path)
        if os.path.basename(os.path.dirname(d)) == PROFILE_DIR:
            try:
                os.rmdir(d)            # drop an empty kbdmap_cores/<core> folder
            except OSError:
                pass
        return True

    def list_maps(self):
        pats = [os.path.join(self.config, "kbd_*.map"), os.path.join(self.config, PROFILE_DIR, "*", "kbd_*.map")]
        return sorted(os.path.relpath(p, self.config) for pat in pats for p in glob.glob(pat))


class RemoteStore:
    remote = True

    def __init__(self, spec, user, password, config_dir):
        m = re.fullmatch(r"(?:([^:@]+)(?::([^@]*))?@)?([^:@]+)(?::(\d+))?", spec)
        if not m:
            raise ValueError("bad --remote '%s', expected [user[:password]@]host[:port]" % spec)
        self.user = m.group(1) or user
        password = m.group(2) if m.group(2) is not None else password
        self.host, self.port = m.group(3), m.group(4) or "22"
        self.config = config_dir
        self.tmp = tempfile.mkdtemp(prefix="kbdmap-")
        askpass = os.path.join(self.tmp, "askpass.sh")
        with open(askpass, "w") as f:
            f.write('#!/bin/sh\nprintf "%s\\n" "$KBDMAP_SSH_PASSWORD"\n')
        os.chmod(askpass, 0o700)
        self.env = dict(os.environ, SSH_ASKPASS=askpass, SSH_ASKPASS_REQUIRE="force",
                        DISPLAY=os.environ.get("DISPLAY", "none"), KBDMAP_SSH_PASSWORD=password)
        self.ssh = ["ssh", "-T", "-p", self.port,
                    "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new",
                    "-o", "NumberOfPasswordPrompts=1", "-o", "LogLevel=ERROR",
                    "%s@%s" % (self.user, self.host)]

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def label(self, path):
        return "%s:%s" % (self.host, path)

    def shell(self, cmd, data=None):
        r = subprocess.run(self.ssh + [cmd], input=data, capture_output=True, env=self.env,
                           stdin=None if data is not None else subprocess.DEVNULL)
        if r.returncode == 255:
            msg = r.stderr.decode(errors="replace").strip() or "ssh failed"
            raise OSError("cannot connect to %s@%s: %s" % (self.user, self.host, msg))
        return r

    def run_ok(self, cmd, data=None):
        r = self.shell(cmd, data)
        if r.returncode != 0:
            raise OSError("command failed on %s: %s" % (self.host, r.stderr.decode(errors="replace").strip()))
        return r.stdout

    def read(self, path):
        q = shlex.quote(path)
        r = self.shell("if [ -f %s ]; then cat %s; else exit 3; fi" % (q, q))
        if r.returncode == 3:
            return None
        if r.returncode != 0:
            raise OSError("cannot read %s: %s" % (self.label(path), r.stderr.decode(errors="replace").strip()))
        return r.stdout

    def write(self, path, data):
        q, qt, qd = shlex.quote(path), shlex.quote(path + ".tmp"), shlex.quote(os.path.dirname(path))
        self.run_ok("mkdir -p %s && cat > %s && mv -f %s %s" % (qd, qt, qt, q), data)

    def delete(self, path):
        q, qd = shlex.quote(path), shlex.quote(os.path.dirname(path))
        cleanup = ""
        if os.path.basename(os.path.dirname(os.path.dirname(path))) == PROFILE_DIR:
            cleanup = "; rmdir %s 2>/dev/null; true" % qd
        out = self.run_ok("if [ -f %s ]; then rm -f %s && echo deleted; fi%s" % (q, q, cleanup))
        return b"deleted" in out

    def list_maps(self):
        out = self.run_ok("cd %s 2>/dev/null || exit 0; for f in kbd_*.map %s/*/kbd_*.map; do [ -f \"$f\" ] && echo \"$f\"; done; true"
                          % (shlex.quote(self.config), PROFILE_DIR))
        return sorted(l for l in out.decode().splitlines() if l)


def open_store(args):
    password = args.password if args.password is not None else os.environ.get("KBDMAP_PASSWORD", "1")
    if args.remote:
        return RemoteStore(args.remote, args.user, password, args.dir or MISTER_CONFIG)
    return LocalStore(args.dir or (MISTER_CONFIG if on_mister() else "."))


def load_table(store, path):
    data = store.read(path)
    return (check_map(data, store.label(path)) if data is not None else None)


# ---------------------------------------------------------------- commands

def cmd_keys(args, store):
    flt = (args.filter or "").upper()
    if flt.startswith("KEY_"):
        flt = flt[4:]
    for code in sorted(KEY_CODES):
        names = KEY_CODES[code]
        aliases = sorted(a for a, c in ALIASES.items() if c == code)
        if flt and not any(flt in n for n in names + aliases):
            continue
        extra = "   aliases: %s" % ", ".join(aliases) if aliases else ""
        print("%3d  %s%s" % (code, " / ".join(names), extra))


def cmd_keyboards(args, store):
    if args.file:
        text = sys.stdin.read() if args.file == "-" else open(args.file).read()
    elif store.remote or on_mister():
        text = (store.read("/proc/bus/input/devices") or b"").decode(errors="replace")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        raise ValueError("use --remote MISTER_IP, run this on the MiSTer, or pipe /proc/bus/input/devices in")
    found = False
    for block in text.strip().split("\n\n"):
        i = re.search(r"Vendor=([0-9a-fA-F]{4}) Product=([0-9a-fA-F]{4})", block)
        n = re.search(r'N: Name="([^"]*)"', block)
        h = re.search(r"H: Handlers=(.*)", block)
        if not (i and h and re.search(r"\bkbd\b", h.group(1))):
            continue
        vid, pid = i.group(1).lower(), i.group(2).lower()
        name = n.group(1) if n else "?"
        note = "  (virtual device, not a real keyboard)" if (vid, pid) == ("0000", "0000") or "Virtual" in name else ""
        print("%s:%s  %s  -> kbd_%s_%s.map%s" % (vid, pid, name, vid, pid, note))
        found = True
    if not found:
        print("no keyboards found", file=sys.stderr)
        return 1


def save_or_delete(store, path, table, what):
    """Write the table; an empty table means 'no remaps', so the file is deleted instead."""
    if not any(table):
        if store.delete(path):
            print("%s: no mappings left, deleted %s" % (what, store.label(path)))
        else:
            print("%s: no mappings, nothing to write" % what)
        return False
    warn_mister_keys(table)
    store.write(path, bytes(table))
    print("%s %s:\n%s" % (what, store.label(path), describe(table)))
    return True


def after_write_hint(store, core):
    if core:
        print("\nPer-core map for %s; it needs the switcher on the MiSTer (./mister_kbdmap.py switcher)."
              % ("every core without its own profile" if core == DEFAULT_PROFILE else "the '%s' core only" % core))
    elif store.remote or on_mister():
        print("\nTakes effect after loading any core, a reboot, or replugging the keyboard.")
    else:
        print("\nCopy it to /media/fat/config/ on the MiSTer (or use --remote IP next time).")


def cmd_map(args, store):
    kbd_id = parse_kbd_id(args.kbd)
    core = parse_core(args.core) if args.core else None
    if not args.mappings:
        raise ValueError("give at least one SRC=DST mapping, e.g. RCTRL=RGUI")
    path = os.path.join(store.config, map_relpath(kbd_id, core))
    table = None if args.replace else load_table(store, path)
    what = "updated" if table is not None else "created"
    table = table if table is not None else bytearray(MAP_SIZE)
    for spec in args.mappings:
        if "=" not in spec:
            raise ValueError("bad mapping '%s', expected SRC=DST, e.g. RCTRL=RGUI" % spec)
        src_txt, dst_txt = spec.split("=", 1)
        src = parse_key(src_txt)
        if dst_txt.strip() == "":
            table[src] = 0
            continue
        dst = parse_key(dst_txt)
        if src == dst:
            raise ValueError("'%s': source and target are the same key" % spec)
        table[src] = dst
    if save_or_delete(store, path, table, what):
        after_write_hint(store, core)


def cmd_remove(args, store):
    kbd_id = parse_kbd_id(args.kbd)
    core = parse_core(args.core) if args.core else None
    if not args.keys and not args.all:
        raise ValueError("give the source keys to unmap, or --all to delete the whole map")
    path = os.path.join(store.config, map_relpath(kbd_id, core))
    if args.all:
        if store.delete(path):
            print("deleted %s" % store.label(path))
        else:
            print("no map file %s" % store.label(path))
            return 1
        return
    table = load_table(store, path)
    if table is None:
        print("no map file %s" % store.label(path), file=sys.stderr)
        return 1
    changed = False
    for k in args.keys:
        code = parse_key(k)
        if table[code]:
            print("removed %s -> %s" % (key_name(code), key_name(table[code])))
            table[code] = 0
            changed = True
        else:
            print("note: %s was not remapped" % key_name(code), file=sys.stderr)
    if changed:
        save_or_delete(store, path, table, "updated")
    else:
        print("nothing changed in %s" % store.label(path))


def cmd_show(args, store):
    core = parse_core(args.core) if args.core else None
    paths = []
    for item in args.items:
        if not store.remote and os.path.isfile(item):
            paths.append(item)
        else:
            paths.append(os.path.join(store.config, map_relpath(parse_kbd_id(item), core)))
    if not args.items:
        rels = store.list_maps()
        if core:
            rels = [r for r in rels if r.startswith("%s/%s/" % (PROFILE_DIR, core))]
        if not rels:
            print("no map files in %s" % store.label(store.config))
            return
        paths = [os.path.join(store.config, r) for r in rels]
    rc = 0
    for p in paths:
        table = load_table(store, p)
        if table is None:
            print("%s: no such map file" % store.label(p))
            rc = 1
        else:
            print("%s:\n%s" % (store.label(p), describe(table)))
    return rc


def cmd_switcher(args, store):
    linux_dir = args.linux_dir or MISTER_LINUX
    script = os.path.join(linux_dir, SWITCHER_NAME)
    startup = os.path.join(linux_dir, "user-startup.sh")
    pidfile = "/tmp/kbdmap_switcher.pid"
    line = "[ -f %s ] && sh %s >/dev/null 2>&1 &  %s" % (script, script, STARTUP_MARK)

    if not (store.remote or on_mister()):          # on a PC: just write the script
        path = os.path.join(args.dir or ".", SWITCHER_NAME)
        with open(path, "w", newline="\n") as f:
            f.write(SWITCHER_SCRIPT)
        os.chmod(path, 0o755)
        print("wrote %s\n\nInstall it with: ./mister_kbdmap.py switcher --remote MISTER_IP" % path)
        print("or by hand: copy it to %s/ and add this line to %s:\n  %s" % (linux_dir, startup, line))
        return

    sh = store.run_ok if store.remote else (lambda c, d=None: _local_run_ok(c, d))
    q = shlex.quote
    stop = "if [ -f {p} ]; then kill $(cat {p}) 2>/dev/null; rm -f {p}; fi".format(p=q(pidfile))
    if args.uninstall:
        sh("{stop}; rm -f {sc}; if [ -f {s} ]; then grep -vF {m} {s} > {t}; cat {t} > {s}; rm -f {t}; fi"
           .format(stop=stop, sc=q(script), s=q(startup), t=q(startup + ".kbdmap.tmp"), m=q(STARTUP_MARK)))
        print("switcher stopped and removed from %s" % store.label(linux_dir))
        print("(per-core profiles in %s/%s were left in place)" % (store.config, PROFILE_DIR))
        return
    store.write(script, SWITCHER_SCRIPT.encode())
    sh("chmod 755 %s 2>/dev/null; true" % q(script))
    sh("[ -f {s} ] || printf '#!/bin/sh\\n' > {s}; grep -qF {m} {s} || "
       "{{ [ -n \"$(tail -c 1 {s})\" ] && echo >> {s}; printf '%s\\n' {l} >> {s}; }}"
       .format(s=q(startup), m=q(STARTUP_MARK), l=q(line)))
    print("installed %s and added it to %s" % (store.label(script), store.label(startup)))
    if args.start:
        sh("%s; KBDMAP_CFG=%s setsid nohup sh %s >/dev/null 2>&1 < /dev/null &" % (stop, q(store.config), q(script)))
        print("switcher (re)started now")
    else:
        print("it starts at the next reboot (or run again with --start to start it now)")


def cmd_status(args, store):
    if not (store.remote or on_mister()):
        raise ValueError("status needs --remote MISTER_IP (or run it on the MiSTer)")
    sh = store.run_ok if store.remote else _local_run_ok
    linux_dir = MISTER_LINUX
    script = os.path.join(linux_dir, SWITCHER_NAME)
    names = sh("printf '%s|%s' \"$(cat /tmp/RBFNAME 2>/dev/null)\" \"$(cat /tmp/CORENAME 2>/dev/null)\"").decode()
    rbf, core = (names.split("|", 1) + [""])[:2]
    print("running core:  file name (RBFNAME) = %s   own name (CORENAME) = %s" % (rbf or "?", core or "?"))
    state = sh("s=; [ -f {sc} ] && s=installed || s='not installed'; "
               "grep -qF {m} {st} 2>/dev/null && s=\"$s, in user-startup.sh\"; "
               "p=$(cat /tmp/kbdmap_switcher.pid 2>/dev/null); "
               "[ -n \"$p\" ] && kill -0 \"$p\" 2>/dev/null && s=\"$s, running (pid $p)\" || s=\"$s, not running\"; echo \"$s\""
               .format(sc=shlex.quote(script), m=shlex.quote(STARTUP_MARK),
                       st=shlex.quote(os.path.join(linux_dir, "user-startup.sh")))).decode().strip()
    print("switcher:      %s" % state)
    rels = store.list_maps()
    live = [r for r in rels if "/" not in r]
    prof = [r for r in rels if r.startswith(PROFILE_DIR + "/")]
    cores = sorted({r.split("/")[1] for r in prof})
    if cores:
        lc = {c.lower(): c for c in cores if c != DEFAULT_PROFILE}
        active = lc.get(rbf.lower()) or lc.get(core.lower()) or (DEFAULT_PROFILE if DEFAULT_PROFILE in cores else None)
        print("profiles:      %s   -> for this core: %s" % (", ".join(cores), active or "none (managed keyboards get no map)"))
    print("\nlive maps in %s (what MiSTer uses):" % store.label(store.config))
    if not live:
        print("  none")
    for r in live:
        print("  %s\n%s" % (r, describe(load_table(store, os.path.join(store.config, r)))))
    print("\nA changed map is picked up after loading a core, a reboot, or replugging the keyboard.")


def _local_run_ok(cmd, data=None):
    r = subprocess.run(["sh", "-c", cmd], input=data, capture_output=True)
    if r.returncode != 0:
        raise OSError("command failed: %s" % r.stderr.decode(errors="replace").strip())
    return r.stdout


def cmd_per_core_rgui(args, store):
    kbd_id = parse_kbd_id(args.kbd)
    src = parse_key(args.key)
    compose = NAME_TO_CODE["COMPOSE"]
    cores = [parse_core(c) for c in (args.rgui_core or ["Minimig"])]
    if src == compose:
        raise ValueError("that key already is the Menu key; you only need the INI lines below")
    path = os.path.join(store.config, map_relpath(kbd_id, None))
    table = load_table(store, path)
    what = "updated" if table is not None else "created"
    table = table if table is not None else bytearray(MAP_SIZE)
    table[src] = compose
    save_or_delete(store, path, table, what)
    print("\nHow it works: the map turns your key into the PC 'Menu' key (KEY_COMPOSE) in every core;")
    print("key_menu_as_rgui=1 then turns that into Right GUI (= Right Amiga) only in the cores below.")
    print("In other cores %s acts as the PC Menu/application key (only matters in PC cores like ao486).\n" % key_name(src))
    print("Add to /media/fat/MiSTer.ini (keep key_menu_as_rgui=0 in [MiSTer]); if a section")
    print("already exists, add just the key_menu_as_rgui line to it:\n")
    for c in cores:
        print("[%s]\nkey_menu_as_rgui=1\n" % c)


# ---------------------------------------------------------------- command line

def main():
    common = argparse.ArgumentParser(add_help=False)
    g = common.add_argument_group("connection and location")
    g.add_argument("--remote", metavar="HOST", help="MiSTer address, [user[:password]@]host[:port]")
    g.add_argument("--user", default="root", help="SSH user for --remote (default root)")
    g.add_argument("--password", help="SSH password for --remote (default 1, or $KBDMAP_PASSWORD)")
    g.add_argument("--dir", help="config folder (default /media/fat/config on the MiSTer or with --remote, "
                                 "else the current folder)")

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("keys", parents=[common], help="list key names and codes")
    p.add_argument("filter", nargs="?", help="only show keys whose name contains this text")
    p.set_defaults(func=cmd_keys)

    p = sub.add_parser("keyboards", parents=[common], help="list keyboards and their VID:PID")
    p.add_argument("file", nargs="?", help="file with /proc/bus/input/devices contents ('-' = stdin)")
    p.set_defaults(func=cmd_keyboards)

    p = sub.add_parser("map", aliases=["create"], parents=[common], help="add mappings to a keyboard's map")
    p.add_argument("kbd", help="keyboard VID:PID, e.g. 046d:404d (see 'keyboards')")
    p.add_argument("mappings", nargs="*", metavar="SRC=DST", help="make key SRC act as key DST")
    p.add_argument("--core", metavar="NAME", help="per-core map ('%s' = all other cores)" % DEFAULT_PROFILE)
    p.add_argument("--replace", action="store_true", help="start from an empty map instead of merging")
    p.set_defaults(func=cmd_map)

    p = sub.add_parser("remove", parents=[common], help="remove mappings (by source key) or a whole map")
    p.add_argument("kbd", help="keyboard VID:PID")
    p.add_argument("keys", nargs="*", metavar="KEY", help="source keys whose mapping to remove")
    p.add_argument("--all", action="store_true", help="delete the whole map file")
    p.add_argument("--core", metavar="NAME", help="per-core map ('%s' = all other cores)" % DEFAULT_PROFILE)
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("show", parents=[common], help="decode map files")
    p.add_argument("items", nargs="*", metavar="KBD|FILE", help="keyboard ids or local files (none = all maps)")
    p.add_argument("--core", metavar="NAME", help="per-core maps of this core")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("switcher", parents=[common], help="install/write the per-core switcher")
    p.add_argument("--start", action="store_true", help="also (re)start it now instead of at the next reboot")
    p.add_argument("--uninstall", action="store_true", help="stop and remove it")
    p.add_argument("--linux-dir", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_switcher)

    p = sub.add_parser("status", parents=[common], help="running core, switcher state and live maps on the MiSTer")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("per-core-rgui", parents=[common], help="make a key act as Right Amiga in chosen cores")
    p.add_argument("kbd", help="keyboard VID:PID, e.g. 046d:404d")
    p.add_argument("key", help="physical key to use, e.g. RCTRL")
    p.add_argument("--core", dest="rgui_core", action="append", help="core for the INI section (repeatable, default Minimig)")
    p.set_defaults(func=cmd_per_core_rgui)

    args = ap.parse_args()
    store = None
    try:
        store = open_store(args)
        return args.func(args, store) or 0
    except (ValueError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    finally:
        if store is not None and store.remote:
            store.close()


if __name__ == "__main__":
    sys.exit(main())
