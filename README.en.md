[🇻🇳 Tiếng Việt](README.md) · **🇬🇧 English**

<p align="center"><img src="assets/voinoi.png" width="160" alt="VoiNoi"></p>

# VoiNoi (Voi Nói)


**Speak Vietnamese into any field on Windows → the text appears right where you need it, no typing.**

A Windows background app: turns spoken Vietnamese into text and pastes it into the field you selected. It also comes with a Reading Assistant (reads documents aloud)
and a voice chat mode with an AI assistant.

Former name: Vietnamese Voice Mic. Renamed to VoiNoi from version 2.0.0.

## What's new in 2.0.1 (complete reading, whole-page reading)

- **Read a whole web page:** with nothing highlighted, `Alt + click` on the page and choose "Read". The app takes the tab's link
  from the address bar (no key presses, the page stays untouched), downloads the main article and reads it without menus,
  table of contents or footer. Pages behind a login fall back to the text shown on screen, minus short menu lines.
- **Highlight is kept:** the `Alt + click` used to fall through to the page and clear the highlight, so "Read" read stale
  clipboard content. Now `Alt + click` no longer reaches the page, and "Read" only uses text copied in the last 10 minutes.
  Disable with `"block_alt_click_passthrough": false`.
- **No skipped passages:** the Edge voice service sometimes returns nothing (`NoAudioReceived`), which used to drop a whole
  passage of about 9 sentences silently. Now it retries with a 1 to 2% speed nudge (inaudible) and falls back to reading
  sentence by sentence. Measured on a 107-passage article: 3 lost passages down to 0.
- **Reading Assistant:** opens whole folders (reads every document inside in order), links with Vietnamese characters,
  very long documents without stalls between passages, waits for the network and resumes at the same sentence,
  and names the exact PDF pages that are images.
- **Fixes:** Kaizen always reported failure under Task Scheduler; Whisper counted noise-only segments as lost words.

## What's new in 2.0.0 (faster, no more freezes)

Measured on a real machine, from the app's logs:

| Action | Before | Now |
| --- | --- | --- |
| Pick "Type" on the radial menu until the mic starts listening | 1 second, sometimes 11 to 16 seconds (whole UI frozen) | 0.26 seconds |
| Opening the microphone for each utterance | about 1 second | 0.03 seconds |
| From recognition done to text pasted | about 3 extra seconds of waiting | pasted immediately |
| Pick "Talk" until the assistant listens | 11 seconds or more | about 2.7 seconds |
| A 36 second clip whose last segment is only noise | 24.8 seconds | 2.7 seconds (11 seconds if Whisper has to re-listen where Google dropped words) |
| Noise (mouse clicks, key presses) mistaken for speech | waited 9 seconds for Whisper, then errored | reported after 0.6 seconds |

Root causes fixed:

- Input field detection used UI Automation on the UI thread. With Chrome and terminals each probe took 2 to 5 seconds, so the radial menu,
  HUD and hotkeys froze. When "Type" was chosen on the radial menu, the app sometimes detected the menu itself and skipped entirely.
  Now choosing "Type" listens immediately, and detection (when the radial menu is off) runs on a background thread.
- Each utterance re-initialized PortAudio 3 to 4 times. Now one shared instance is kept ready, and plugging or unplugging the mic is still detected.
- The vocabulary learning function re-read the config file almost 3,000 times per sentence, before pasting. Now it is cached and runs after pasting.
- When Google could not recognize a segment, the app retried sequentially up to 14 times. Now it resends and splits in parallel, and Whisper rescues
  the broken segment while the other segments are still running.
- Noise-only segments counted as 0% errors, pulling confidence below 82% and forcing Whisper to re-listen to the whole clip. Now noise segments
  do not count as lost words.
- Whisper often hallucinated sentences like "Please subscribe to the channel..." on noise. These are now filtered out of Whisper's output.
- For any segment where Google returns too few words for its length (often dropping the first sentence), the app has Whisper listen to that segment
  alone and keeps the more complete version. Tune the threshold with `low_coverage_wpm` (default 92, set 0 to disable).
- "Talk" mode: the AI brain is detected in the background and remembered for 10 minutes, the greeting is shorter and its voice is pre-generated.

## Quick start

1. Run `Start VoiNoi.cmd` (source build) or `VoiNoi.exe` (packaged build).
2. Hold `Alt` and left-click the chat box or input field you want to type into. A radial menu appears:
   top = Type, left = Read, right = Talk, bottom = Cancel.
3. Choose "Type" and speak. When you stop speaking, the app recognizes and pastes into the exact spot you `Alt + click`ed.
4. Want to stop early while it is listening: press `Esc`, what you already said is still recognized.
5. Paste failed or you switched windows: press `Ctrl+V` to paste again, the latest text is always on the clipboard.

Create a VoiNoi shortcut with icon on the Desktop and Start Menu:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-shortcut.ps1
```

## Radial menu modes

- Type: speech to text into the selected field.
- Read: highlight a passage to read just that. With nothing highlighted in a browser, it reads the whole article on the open page.
  Outside a browser it reads what you `Ctrl+C`ed in the last 10 minutes. Otherwise the Reading Assistant window opens.
- Talk: voice chat with the AI assistant.
- Cancel: `Esc`, click outside, or leave it for 10 seconds.
- Turn off the radial menu (`Alt + click` types immediately): `"enable_radial_menu": false` in `voice-mic-settings.local.json`.

## Voice chat

- Open: `Alt + click` then choose "Talk", or press `Ctrl+Alt+V` anywhere (change it with `voice_chat_hotkey`).
- Or choose "Type" and say "trò chuyện", "nói chuyện" or "voice".
- Pause: say "tạm dừng", "chờ chút", or press `Ctrl+Alt+V`. Resume: `Alt + click` or `Ctrl+Alt+V`.
- Stop completely: say "thôi", "dừng lại", "cảm ơn em", or press `Esc`. About 12 seconds of silence also ends it.
- The AI brain is picked in this order: Claude API (with `ANTHROPIC_API_KEY` set and `anthropic` installed), Claude Code CLI
  (logged in), local Ollama (`qwen2.5:7b`). Force one with `voice_chat_backend`: `auto`, `claude-api`, `claude-cli`, `ollama`.
- Each conversation is saved in `reader-data/conversations/`.

## Document Reading Assistant

Reads documents, notes and research papers aloud in a natural Vietnamese voice (Hoài My, Nam Minh).

- Open: run `Start Doc Reader.cmd`, or drag and drop a file onto it.
- Input: txt, md, pdf with a text layer, docx, html, epub, a whole folder, web links, public Google Docs, whatever you just `Ctrl+C`ed.
- Hand it a job from the command line: `"Start Doc Reader.cmd" "E:\Books\abc.pdf"` opens and starts reading.
- Shortcuts: `Space` read or pause, left and right arrows to move between sentences, `N` take a note, `Q` ask a question, `R` reread the sentence.
- Notes are saved as Markdown in `reader-data/notes/`. Runs locally at `http://127.0.0.1:8767`.
- Needs Internet to generate the voice (`edge-tts`), audio is cached in `reader-data/tts-cache/`.

## Microphone settings

Edit `voice-mic-settings.local.json` (per machine, not pushed to GitHub):

```json
{
  "preferred_microphone": "BKD-11 Pro Audio",
  "microphone_name_hints": ["USB Audio Device", "Microphone", "Headset"],
  "enable_whisper_fallback": true,
  "whisper_model": "small"
}
```

Leave `preferred_microphone` empty and the app picks one from the hint list.

## Recover what you just said

- `Ctrl+V` pastes the latest text again.
- `voice-last.txt`: latest text. `voice-transcripts.jsonl`: history. `voice-last.wav`: latest audio.
- These files stay on your machine and are already in `.gitignore`.

## Run from source

Requirements: Windows 10 or 11, Python 3.10 or later, a microphone, Internet (Google Speech Recognition).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

To use Whisper as a fallback when Google cannot hear (a few hundred MB):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-whisper.txt
```

Run: `Start VoiNoi.cmd` (closes any old running instance, keeps only one).

## Start with Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\install-startup.ps1
```

Remove: `uninstall-startup.ps1`.

## Build a release

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Output:

```text
dist\VoiNoi\VoiNoi.exe
releases\VoiNoi-windows.zip
releases\version.json
```

The `.exe` does not bundle Whisper to stay small. The `ducdg88/voinoi` repo used to be private, so auto-update is off by default
(`auto_update_enabled: false`): the app cannot download files from a private Release. Now that the repo is public, you can turn
`auto_update_enabled` back on and upload both `VoiNoi-windows.zip` and `version.json` to each GitHub Release.

## Troubleshooting

- Voice not picked up: check the mic in Windows and `preferred_microphone`.
- Many wrong words: speak closer to the mic, reduce background noise, add keywords to `speech_context_terms`.
- Not pasted in the right place: `Alt + click` exactly on the input field before choosing "Type".
- See every step in detail (with millisecond timestamps): `voice-mic.log`.

## Key files

- `voice_mic_icon.py`: main app code.
- `reader/`: Reading Assistant and voice chat. `doc_reader.py`: opens the Reading Assistant.
- `voice-mic-settings.json`: default config. `voice-mic-settings.local.json`: per machine config.
- `voice-context.json`: default vocabulary. `voice-context.local.json`: vocabulary the app learns on this machine.
- `Start VoiNoi.cmd`, `Start-VoiNoi.ps1`: run from source.
- `build.ps1`, `updater.ps1`: packaging and auto-update.
- `install-shortcut.ps1`, `install-startup.ps1`, `uninstall-startup.ps1`: shortcuts and start with Windows.
- `assets/`: VoiNoi icon and the script that draws it (`make_icon.py`).


---

Made by [DUCPT](https://ducpt.com/?utm_source=github&utm_medium=readme&utm_campaign=voinoi): AI agents, automation and digital products for one-person businesses. This tool: https://ducpt.com/bai-viet/vietnamese-voice-mic-coding-bang-giong-noi/?utm_source=github&utm_medium=readme&utm_campaign=voinoi
