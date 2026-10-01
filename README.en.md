# KeyPresser

![KeyPresser](assets/header.png)

![platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078D6)
![python](https://img.shields.io/badge/python-3.8%2B-3776AB)
![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
![license](https://img.shields.io/badge/license-MIT-green)
![version](https://img.shields.io/badge/version-1.0.1-blue)

![CI](https://github.com/hcb9291/KeyPresser/actions/workflows/ci.yml/badge.svg)

**English** | [简体中文](README.md)

A small Windows utility that **repeats keystrokes on a set interval**. Repeat a
single key, or line up several keys and run them in a loop — each step with its
own delay. Global hotkeys, sound cues, and an option to only work while a
specific application is in the foreground.

![KeyPresser UI](assets/screenshot.png)

It is written with the Python standard library only (tkinter for the UI), so
there is **nothing to `pip install`**. The interface has a soft pink, rounded-card
look with an original "cat-ear keycap" mascot — the icon, the mascot, the banner
and the sound effects are all drawn or synthesized by code, not taken from
anywhere.

> The application's interface is in Chinese; this document and the source
> comments explain everything you need to use it.

---

## Download & install

### Option 1 — prebuilt exe (recommended for non-developers)

Download `KeyPresser.exe` from the
[Releases](https://github.com/hcb9291/KeyPresser/releases) page and double-click it.
**Python is not required.**

The exe is not code-signed, so Windows SmartScreen may show "unknown publisher"
the first time — click **More info → Run anyway**.

### Option 2 — run from source

Python 3.8 or newer (tkinter is included on Windows). Nothing else to install:

```
python main.py
```

You can also double-click `run.bat`. `python main.py --version` prints the
version and exits.

### Option 3 — build your own exe

Double-click `build.bat`. It creates a virtual environment, installs PyInstaller
and produces a single-file, self-contained `dist\KeyPresser.exe`.

---

## Features

### Key sequence

- Pick a key from the drop-down (F1–F12, letters, digits, space, Enter, arrows,
  and more) and add it to the list.
- **One key in the list = repeat that key. Several keys = run them in order, in
  a loop.**
- Every step has its own interval (double-click a row to edit it).
- Remove, move up or move down to reorder the steps.
- A separate setting for how long each key is held down (milliseconds).

### Global hotkeys

`F8` starts and `F9` stops from any window, and both can be changed
(`Ctrl+Alt+K`-style combinations work). Clicking the buttons on screen does the
same thing.

### Sound cues

A sound plays on start and on stop, from one of three sources:

1. **Built-in chimes** — three sets (bright / soft / deep). The start cue rises,
   the stop cue falls and lasts longer, so you can tell them apart by ear without
   looking at the screen. All synthesized in code, free to use.
2. **Your own audio** — import a `.wav` file, or record one with your microphone
   right in the app.
3. **Windows speech** — reads “开始按键 / 停止按键” using a voice installed in
   Windows. You can add more voices in Windows settings and refresh the list.

### Scope

- **Global** — repeats everywhere, in any window.
- **Selected application** — only while the chosen program is in the foreground.
  It pauses when you switch away and continues when you switch back.

### Themes

A theme button in the top-right corner switches the skin and remembers your
choice. Four themes ship with the app:

| Theme | Look |
| --- | --- |
| Sakura Light | pink (default) |
| Sakura Dark | pink, easier on the eyes at night |
| Mint Light | teal / green |
| Night Dark | deep blue with cyan accents |

---

## Quick start

1. Pick a key in the “key sequence” card and click add (add more steps if you
   need several keys, or if you want a long rhythm).
2. Choose a sound source and click preview to make sure you can hear it.
3. Choose the scope — leave it on “global” unless you want it tied to one app.
4. Set the start / stop hotkeys.
5. Press `F8` to start and `F9` to stop, or use the buttons at the bottom.

---

## Files

| File | What it is |
| --- | --- |
| `main.py` | the whole program (UI, key sending, hotkeys, sound, themes) |
| `themes.json` | **the theme data file**: one set of colours per theme — edit colours or add themes here |
| `tts_synth.ps1` | calls the Windows speech synthesizer to turn text into a wav (only used by “Windows speech”) |
| `assets/icon.ico` / `icon.png` / `icon_512.png` | program icon (window, taskbar, exe) |
| `assets/mascot.png` | the mascot used in the banner |
| `assets/header.png` | banner image for the repository page |
| `assets/screenshot.png` | the UI screenshot above |
| `assets/social_preview.png` | 1280×640 image used for GitHub's social preview |
| `sounds/*_start.wav` / `*_stop.wav` | the three built-in sound sets (chime / soft / deep) |
| `tools/make_assets.py` | the script that generates every icon and sound |
| `tools/selfcheck.py` | project self-check (assets, theme data, privacy scan) |
| `build.bat` / `run.bat` | build an exe / run the app |
| `docs/RELEASING.md` | how to cut a new release |
| `CHANGELOG.md` | version history |

Settings and your recorded audio are **not** written next to the program —
they live in:

```
%APPDATA%\KeyPresser\settings.json          settings
%APPDATA%\KeyPresser\custom_voice\          your imported / recorded start and stop sounds
%TEMP%\keypresser_tts\                      cache for the Windows speech synthesis
```

So the program folder always stays clean, with just the program file in it.

---

## Custom themes

Theme data lives in `themes.json`: each theme is an `id`, a `name` and a
`colors` block of 25 colour keys (background, card, border, title, body text,
hint text, accent, stop colour, fields, tables, …).

At startup the program looks for the file in this order: **next to the program
(exe or script) → inside the packaged resources**. So there are two ways to make
it yours:

1. copy `themes.json` next to the exe and edit it (that copy wins);
2. or edit `BUILTIN_THEMES` in the source — the fallback used when the file is
   missing (it must stay identical to the file).

Restart the app afterwards; switching still happens through the theme button in
the top-right corner.

---

## Assets & licensing

Every icon, the mascot, the banner and the built-in sound effects are
**generated by code** (`tools/make_assets.py`) — no third-party assets are
bundled:

- `assets/icon.ico`, `icon.png`, `icon_512.png`, `mascot.png`, `header.png`,
  `social_preview.png`: drawn by code; the character is original (a cat-eared
  keycap) and does not reference or include any existing work or character;
- `sounds/chime_*.wav`, `soft_*.wav`, `deep_*.wav`: synthesized from sine waves.

They are therefore free of any asset-licensing issues and can be used freely
with this project (which is MIT licensed).

“Windows speech” calls the speech engine **on the user's own machine** at run
time — no audio is distributed with the repository. “Your own audio” uses
whatever the user supplies or records.

> A note for anyone modifying this project: do not bundle audio generated by or
> downloaded from third-party voice services (online TTS sites, dubbing tools,
> …) into the repository — those usually are not licensed for redistribution.

---

## FAQ

**The hotkey does nothing.**
Most likely another program already registered it. Pick a different
combination, or use the buttons in the window.

**Keystrokes don't reach the target program.**
If that program runs **as administrator**, this tool has to run as
administrator too — that is Windows' privilege isolation, not a bug here.

**It doesn't work in a game.**
Simulated input is ignored or blocked by anti-cheat systems. That is expected;
this tool is not designed for games.

**Importing a sound fails.**
Only `.wav` files are accepted. Convert other formats first with the Windows
recorder or with the built-in “record” feature.

**Hotkeys or recording appear to do nothing, or the window looks wrong.**
In a sandbox, virtual machine or otherwise restricted environment, the window
and audio APIs can be blocked. Run it on a normal desktop session.

---

## Known limitations

- Windows only (`SendInput`, `mciSendString`, Windows speech and other system
  APIs are used);
- importing custom audio only accepts `.wav`;
- if the target program runs as administrator, this tool must too;
- keystrokes are simulated, so strict anti-cheat systems may ignore them.

---

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md)
(in Chinese) for the conventions, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
for the code of conduct. Please report security problems privately, as described
in [SECURITY.md](SECURITY.md).

Version history is in [CHANGELOG.md](CHANGELOG.md); the release process is
described in [docs/RELEASING.md](docs/RELEASING.md).

---

## Disclaimer

This tool automates repetitive keystrokes. Follow the terms of service of the
software you use it with; using automation in online games or other online
services may violate their user agreements. Use at your own risk.

## License

[MIT](LICENSE)
