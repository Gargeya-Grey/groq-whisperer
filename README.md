# Groq Whisperer

Hold a hotkey, speak, release (or press again), and the transcript is pasted into whatever app is focused. Transcription uses Groq’s Whisper API (fast, free-tier API key).

This is a Windows-friendly fork of [KennyVaneetvelde/groq_whisperer](https://github.com/KennyVaneetvelde/groq_whisperer). The original “hold Pause, release to stop” flow **does not work on typical PC keyboards**: Pause/Break often never sends a key-up, so the app would keep recording forever. This fork fixes that and the Windows paste path.

## Keys

| Key | Behavior |
|-----|----------|
| **Pause** | Press once to **start**. Press again to **stop**, transcribe, and paste. |
| **F8** | **Hold** to talk, **release** to stop (reliable on laptops that hide Pause behind Fn). |
| **Esc** | Quit |

Click the text field first. After stop, wait for Groq (usually under a second). If paste misses, **Ctrl+V** — the text is already on the clipboard.

Clips shorter than ~0.4 seconds are ignored so you do not get empty or prompt-echo garbage.

## Why Pause is a toggle

On IBM-style PC keyboards, **Pause does not send a key-up**. Hold-to-talk cannot see “release Pause.” This repo registers Pause as a Windows hotkey instead: each press is start or stop. **F8** is real hold-to-talk for laptops without a usable Pause key.

## Setup

You need **Python 3.10+** (3.13 works) and a microphone.

### 1. Clone

```bash
git clone https://github.com/Gargeya-Grey/groq-whisperer.git
cd groq-whisperer
```

### 2. Virtualenv and install

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`PyAudio` ships a Windows wheel. On Linux you may need PortAudio (`sudo apt install portaudio19-dev`) before `pip install`.

### 3. Free Groq API key

1. Open **https://console.groq.com/keys**
2. Sign in (Google / GitHub / email)
3. **Create API Key** and copy it (shown once)

This session only (PowerShell):

```powershell
$env:GROQ_API_KEY = "your_key_here"
```

Command Prompt:

```bat
set GROQ_API_KEY=your_key_here
```

Permanent (new terminals after this):

```bat
setx GROQ_API_KEY "your_key_here"
```

macOS / Linux:

```bash
export GROQ_API_KEY="your_key_here"
```

Do not commit the key. Do not put it in the repo.

### 4. Run

Windows: double-click `start.bat`, or:

```bat
venv\Scripts\python.exe main.py
```

If the hotkey does not reach other apps, run the terminal **as Administrator**.

## Troubleshooting

| Symptom | What to do |
|---------|------------|
| Pause starts but never stops | Use **Pause again** (toggle), not release. Or hold **F8**. |
| Another app already uses Pause | Close it, or use F8. |
| Paste does nothing | Click the text field first; then Ctrl+V. Try Run as administrator. |
| `GROQ_API_KEY is not set` | Set the variable in **that** window, or `setx` and open a new one. |
| Empty / nonsense transcript | Speak longer than half a second; check the mic. |
| Linux: `pyaudio` build fails | Install `portaudio19-dev` (or equivalent), then pip again. |

## Credits

- Original project: [KennyVaneetvelde/groq_whisperer](https://github.com/KennyVaneetvelde/groq_whisperer) (MIT)
- Windows Pause hotkey, F8 hold-to-talk, paste, and short-clip handling: this fork

## License

MIT. See [LICENSE](LICENSE).
