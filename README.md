# OCEANBOILER 0.4 — KTMP1 Bass Workstation

A standalone Linux desktop instrument for the **KAT KTMP1**. A new project with its own engine and sessions; no Chipforge code, assets, dependencies, or project format. All sounds are procedural synth voices. No chiptune oscillators, samples, accounts, API keys, or subscriptions.

## Start on Manjaro / Arch

Use your normal desktop user, not root. With PipeWire already working:

```bash
sudo pacman -S --needed python python-pip portaudio libsndfile alsa-lib
```

For PipeWire's JACK route, install `pipewire-jack` if it is not already installed. Pacman may propose replacing a conflicting JACK provider: review that against your existing audio setup. Do not install a second audio server or replace a working PulseAudio setup blindly. The app can also use an available `pipewire`, `pulse`, or `default` PortAudio output.

```bash
cd Oceanboiler-0.4
bash install.sh
bash run.sh
```

The installer creates a local `.venv`; it does not install Python packages system-wide. `run.sh` uses `pw-jack` when available, requests 256/48000 latency, and limits numerical-library worker threads. This is a requested graph setting, not a promise of total pad-to-speaker latency. The app shows PortAudio's reported output latency and xrun count. Start at 256 frames; try 512 if it crackles. Restart audio with the button after changing output or buffer size. It expects a 48 kHz stereo output.

If a Qt plugin fails on your desktop, run `QT_DEBUG_PLUGINS=1 bash run.sh` to identify the missing system library. A headless inspection is supported with `QT_QPA_PLATFORM=offscreen .venv/bin/python app.py --no-audio --smoke-test`.

## First minute with the KAT

1. Power the KTMP1 using its normal power arrangement and connect its USB cable to the computer. USB carries MIDI; this software generates audio on the computer.
2. Launch. A KAT/KTMP/USB-MIDI-named input is automatically connected if found. Otherwise choose the input and press **Connect**. Use **Refresh** after reconnecting USB.
3. Click **Learn all 4 KAT pads**. Strike each physical pad once, in the order you want mapped to voices 1–4. These start as Growl, Talking bass, Reese, and Sub drop. The hit used to learn also plays the voice.
4. If two pads send the same note, the app warns rather than silently remapping. On the KAT choose its MIDI-note mode, strike the pad, and use VALUE +/- to give it a distinct note (for example 36, 38, 40, 41). The software does not assume factory note assignments. Reset the app's mapping before a fresh full remap if needed.
5. For a conventional kit, select a software pad and change its Engine to Kick, Snare, or Hat. You can map a physical pad to any of the eight software voices using **Learn selected pad**. The kick trigger can also be learned. The hi-hat input is a controller for an H1/H2-assigned pad; do not assume it emits an independent strike note. Learn only notes actually seen in the monitor.
6. Click **Demo beat**, then **Play**. Play the four bass voices over the synth drums. Toggle drum lanes off using their mute checkboxes if you want the beat to leave more room.

Keyboard **1–8** triggers voices; **Space** toggles transport; **Esc** stops transport and clears all voices and delay. Keys are deliberately not intercepted while editing text, numbers, or dropdowns. Click a pad or empty area to return keyboard focus to performance.

## Sound design

- **Growl:** sine-FM carrier, moving modulation index, resonant low-pass, saturated upper harmonics, separate fundamental.
- **Talking bass:** FM excitation into two moving formant bands with a sub underneath.
- **Reese:** two detuned harmonic oscillator banks, filter movement, saturation, sub reinforcement.
- **Sub drop:** continuous-phase pitch fall with a smooth envelope.
- **Kick:** exponential pitch envelope, sub body, short filtered noise transient.
- **Snare:** tuned body and filtered noise burst.
- **Hat:** high-passed noise and inharmonic metal oscillators.
- **Metal:** inharmonic FM percussion through a resonator.

Four starting kits: **Abyss**, **Bog ritual**, **Chrome teeth**, **Deep pressure**. They are original patches aimed at experimental bass/dubstep textures, not samples or reproductions of any artist's sound.

Select a pad to edit engine, MIDI pitch, decay, tone, motion depth, drive, LFO speed, level, pan, and delay send. Voice edits are captured on the next hit. MASTER, MOTION, GRIT, SPACE, FEEDBACK, BPM, and SWING operate on the active engine. Master modulation changes are block-updated; this first version is not a fully smoothed automation engine.

The wobble speed is cycles per quarter-note beat: 1 = quarter-note wobble, 2 = eighth-note wobble, 4 = sixteenth-note wobble; 1.5 and 3 give dotted/triplet-related rhythms. Each struck voice restarts its own wobble phase. One-shot envelopes deliberately ignore note-off messages. Bass lanes choke their previous voice with a short release; up to 32 voices are retained overall. Kick voices duck lanes 1–4. A ping-pong dotted-eighth delay supplies space; there is no convolution reverb or external effects dependency. Master DC removal and soft limiting contain output peaks, but do not protect hearing from excessive speaker volume.

## Sequencer and recording

The grid is two bars of 4/4 at sixteenth-note resolution. Left-click toggles a step; right-click cycles soft/medium/accent velocities. Check the row label to mute it. **Overdub hits** records pad and keyboard performances to the nearest sixteenth while transport runs. Quantization is approximate with swing enabled. Sequencer timing is driven by sample counts, not the GUI timer. MIDI hits begin at the next audio callback, not at a sample-accurate USB timestamp.

**Record WAV** writes the live stereo master as a 24-bit WAV on a background thread. Stop recording to finalize the file before opening it elsewhere. Disk errors and dropped blocks are surfaced in the UI; if either happens, the recording is incomplete. Changing audio outputs is blocked during recording.

**Save / Load** uses readable JSON, including patches, steps, mutes, macros, mapping, and MIDI response settings. Autosave writes `~/.config/wubforge/autosave.json` (or `$XDG_CONFIG_HOME/wubforge/autosave.json`) every 30 seconds and on clean exit. Session loading stops the sequencer. The selected operating-system audio/MIDI port is not saved because port identifiers can change after reconnecting hardware.

## KTMP1 MIDI facts and limitations

The manufacturer's MIDI implementation chart specifies channel **10**, note-on velocity **1–127**, and note-off represented as note-on with velocity zero. It does not specify transmission of aftertouch, pitch bend, program changes, or MIDI clock. The pad's internal knobs/settings therefore cannot be treated as general-purpose external synth controls. Manual sections 3.3 and 3.7 also warn that changing an internal voice changes its MIDI note. Set internal voices first, then learn the pads. The MIDI-note adjustment range in the manual is 00–99; the software accepts the full 0–127 MIDI range.

The app's MIDI monitor displays note-on and note-off traffic, including the channel and velocity. No undocumented 'KAT fix' is assumed. A low default velocity-curve exponent boosts lighter hits; lower values boost them further. Min velocity rejects weak events. Retrigger suppression is **off by default** because unnecessary filtering can eat rolls/flams. If you see actual duplicate strikes, try 5–10 ms and check that your playing still tracks correctly. This does not repair a physical sensor fault or recover missing USB events.

The computer cannot distinguish two physical pads that transmit the same channel/note. Set distinct notes on the KAT. Likewise, missing notes or constant velocity at the hardware source cannot be reconstructed reliably by software.

Sources consulted:
- KAT KTMP1 manufacturer manual, sections 1, 3.3, 3.7, and 4.2: https://www.katpercussion.com/static/pdf/KTMP1_WorldManual_English.pdf (current manual retrieved during the 0.2 research pass).
- Manufacturer manual directory: https://www.katpercussion.com/manuals.html
- PipeWire JACK wrapper: https://docs.pipewire.org/1.6/page_man_pw-jack_1.html
- PipeWire latency: https://docs.pipewire.org/devel/page_latency.html
- python-sounddevice callback API: https://python-sounddevice.readthedocs.io/en/latest/api/streams.html

## Troubleshooting

- **Nothing in MIDI dropdown:** check power/cable, then run `aconnect -l` or `amidi -l` from `alsa-utils`. Unplug/replug and refresh; USB hotplug does not silently rebind an open port in this version. If the monitor shows a channel other than 10, choose channel 0 (all) while diagnosing.
- **Monitor works but no sound:** learn that note, unmute the target lane, turn up its level and MASTER, then check computer output routing.
- **Keyboard works but pads don't:** check MIDI input, channel, mapping, and threshold. Hardware ASSIGN changes can invalidate the mapping.
- **Audio on but silent:** verify the selected output and PipeWire graph, e.g. in an existing graph patchbay or desktop sound control. Use wired headphones/speakers for performance; Bluetooth commonly adds substantial latency.
- **No JACK output:** install/enable the appropriate PipeWire JACK client support, or select a working PipeWire/PulseAudio/default output. `pw-jack` redirects JACK clients; it does not create a PipeWire server.
- **Crackles:** try 512/1024 frames, reduce long overlapping voices, and watch xruns. Python callback execution is not hard realtime; other Python activity, disk I/O, and OS scheduling can still cause underruns.

## Verification and scope

This release was tested in a headless Linux build environment, not against your attached physical KTMP1 or your PipeWire graph. Automated tests cover synth finiteness and peak bounds across engines, voice cleanup, MIDI channel/velocity-zero handling, mapping collision rejection, swing/sample scheduling, panic, session roundtrip, and WAV finalization. A GUI smoke test opens the actual Qt window, triggers a voice, round-trips a session, and takes a screenshot. A deterministic offline demo is included as `oceanboiler-demo.wav`.

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python app.py --render-demo another-demo.wav
```

A 1,000-block demo-engine benchmark in the build environment measured roughly 0.53 ms mean and 1.06 ms p99 per 256-frame callback payload, versus 5.33 ms of audio at 48 kHz. This excludes actual driver scheduling, MIDI transport, and output hardware, and is not a guarantee for your machine. NumPy/scipy allocate during processing; this is a practical first-pass Python workstation, not a certified hard-realtime audio engine. Nonlinear saturation/FM are not oversampled in this version, so extreme settings can alias.

## Files

- `app.py`: PySide6 desktop interface, session workflow, PortAudio stream.
- `engine.py`: synth voices, DSP, sample-clock sequencer, effects.
- `io_layer.py`: KTMP1-compatible routing and asynchronous recording.
- `run.sh`, `install.sh`, `requirements.txt`: isolated Linux launch/install.
- `tests/`: reproducible regression tests.
- `oceanboiler-demo.wav`, `ui-preview.png`: rendered output and UI preview.

No external network access occurs while playing. Installation requires downloading dependencies.


## 0.2 — instrument panel and hardware routing

The KAT tab displays exactly six physical connections: Pad 1–4, Kick trigger, and Hi-hat controller. Each row has a learned/manual note and a target sound lane. The eight buttons are software lanes, not physical inputs; they remain for old sessions and sequencing. A lane may use any engine or preset. Learn an input, then change its Lane dropdown to play another instrument. Legacy MIDI maps remain active when loading old sessions; their physical pad identities cannot be inferred from note numbers, so the six rows start unlearned until you explicitly assign them.

The hi-hat controller is not equivalent to a sixth strike pad. It controls open/closed sounds on the last pad assigned to H1/H2. CC events are displayed diagnostically, not synthesized into strike events. If the controller does not emit an independent note, leave its row unlearned. No CC4 support or physical pedal event is assumed.

**Change sounds:** select one of the eight sound lanes → SOUND BANK → search or select a category → pick a preset → Load to selected lane or Load + play. A double-click loads and plays. Hardware note assignments stay fixed when changing the software instrument. Editing Engine directly also works. Updates take effect on the next strike.

The bank contains **52 original presets across 13 engines**, not downloaded artist patches: the original eight engines plus Rubber wub, Scratch, Weeewhaa, Bubble, and Neuro. Scratch reverses through a procedurally generated harmonic/noise tape. Weeewhaa sweeps pitch upward then back down (or downward with negative sweep), while the formant moves in opposition. Bubble uses a short exponential pitch contour. Neuro adds nested FM and moving spectral cancellation. Rubber wub uses a resonant sweep over a finite harmonic oscillator.

The expanded editor provides FM ratio, pitch sweep in semitones, and texture, enabled only for engines that use them. Save selected sound as preset writes user patches separately to `~/.config/wubforge/user-presets.json`; duplicate names receive a numeric suffix. Factory presets stay intact. Prior sessions load using default values for the new parameters. The session now also stores the six hardware assignment rows.

UI compatibility: icon-theme lookup is disabled for this app to avoid unsupported desktop SVG properties. The launcher prefers X11/XWayland when DISPLAY exists, while preserving an explicit QT_QPA_PLATFORM override. These workarounds have not been validated on your actual desktop. Launch with `QT_QPA_PLATFORM=wayland bash run.sh` if you need native Wayland.

Upgrade: extract this package in a separate directory, run install.sh there, and launch. It uses the existing config/session location and reads older sessions. Keep the old directory if you want an easy rollback; 0.2 writes new patch fields that the old app cannot read. The first legacy autosave is preserved as autosave-before-0.2.json before migration; use that copy when downgrading. Existing installation files and saved presets are not deleted by the installer.

Focused research used the manufacturer's manual above, Ableton's filter-envelope recipe https://learningsynths.ableton.com/recipes/wow-bass and the oscillator/formant concepts at https://docs.native-instruments.com/ni-tech-manuals/massive-manual/en/oscillator-section . The implemented patches are original engineering choices, not exact emulations. The additional nonlinear/variable-rate engines are not oversampled; extreme settings can alias.


## 0.3 — simpler performance view

PLAY opens with eight color-coded software sound pads, four primary macros, and a waveform. Each pad shows its keyboard number and hardware assignment. A white outline marks the selected voice, a yellow outline and explicit text request a learning hit, and strikes flash in the pad's own color. Learn 4 KAT pads now also fills the named hardware rows. The six physical inputs remain in SETUP; eight software voices are retained for compatibility.

The large red **RECORD AUDIO** button stays at the top on every tab. It opens the WAV save dialog and records the stereo master. While running it reads **STOP** plus elapsed minutes/seconds. Press Stop to finalize the file. This is separate from **Overdub hits** in BEAT, which writes sequencer steps rather than audio.

SOUNDS contains the searchable preset bank, selected-lane dropdown, kit selector, and detailed editor. BEAT contains the sequencer, demo/clear controls, overdub, feedback, and swing. SETUP contains devices, hardware assignments, MIDI calibration, and monitor. Audio and MIDI readiness stay visible above the tabs. Press a pad, then Change selected sound to open the browser.

This update changes layout and visual feedback; synth DSP, preset data, and session format are unchanged from 0.2. Extract Oceanboiler-0.4 separately to preserve your previous installation.


## 0.4 — Oceanboiler and Sound Forge

The application, window title, audio node, and new default filenames are now **Oceanboiler**. Configuration lives in `$XDG_CONFIG_HOME/oceanboiler` (normally `~/.config/oceanboiler`). On first launch, autosave.json and user-presets.json are copied from the legacy wubforge config directory only when the new files do not exist. The original files remain untouched. Later launches use Oceanboiler's own settings. Earlier mentions of the wubforge config directory in this document describe legacy versions.

**SOUND FORGE** builds one instrument from up to three independent procedural synth layers. Start with Sub sine + Growl + Scratch, then change each engine and blend their mix levels. Any available engine can occupy any layer; SUB/BODY/TEXTURE are useful role labels, not restrictions. Controls include layer on/off, transpose, pan, tone, motion, drive, and engine-specific FM ratio, pitch sweep, and texture. The root pitch, duration, tempo-synced wobble rate, output level, and delay send apply to the instrument. Unused controls are disabled. Each layer has the existing engine's envelope and modulation behavior; custom drawn envelopes, wavefolding, arbitrary modulation routing, and source-code plugins are not implemented in this first Sound Forge.

1. Choose a target lane and name your sound.
2. Edit the three layers; click **Apply + play** to audition your draft.
3. **Save instrument** adds it to the User sound bank. The name entered in the save dialog is the browser preset name; the Forge name labels the voice on its pad.
4. **Export patch** saves a portable, validated JSON document. **Import patch** loads into the draft without altering your current lane until you Apply.
5. **Load selected lane into Forge** edits the selected custom instrument or starts a one-layer draft from an existing voice.

Custom layered voices show their names on Play. Their simpler Sounds-tab editor is disabled; edit them in Sound Forge. A regular factory preset can still replace any lane. Sessions retain all layer data, and previous non-layered sessions still load with defaults. Layered patches use format `oceanboiler.patch`, version 1. No Chipforge source or instruments were imported; integration with Chipforge remains future work requiring its source. Oceanboiler is independent.

Mute checkboxes now explicitly say **MUTE**. Muted Play pads turn gray and display **MUTED**. Checked still means muted.

DSP cost scales with enabled layers: a 32-voice cap can contain up to 96 child synth voices. This version has not been benchmarked on the user's machine at that maximum. Raise the buffer if heavy layering causes underruns. Existing master soft limiting remains in place.

Extract into the new Oceanboiler-0.4 folder, run `bash install.sh`, then `bash run.sh`. No old installation files are modified. This package contains full source and has no runtime cloud dependency. Oceanboiler is released under the GNU General Public License v3.0. See LICENSE.