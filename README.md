# J.A.R.V.I.S - Windows AI voice assistant

Python 3.11 or 3.12 recommended (3.13 works only if all wheels exist for your packages), Windows 10/11.

## 1. Install and start
```
python -m venv .venv
.venv\Scripts\activate
python install_deps.py
python main.py
```
`install_deps.py` installs every package one by one (a single failing package does not block the rest). If anything is missing, J.A.R.V.I.S shows a banner in SETTINGS with an **INSTALL MISSING PACKAGES** button. Always start it from the activated `.venv`.
Open the folder in Visual Studio Code, select the `.venv` interpreter, run `main.py`.

## 2. What happens at start
1. Loading screen (your HUD-circle picture, animated) while microphone, Gemini, voice and mail are checked. It never hangs: after 14 s it continues even if a service is offline.
2. Main window with the particle reactor (HOME), SETTINGS, BRAIN.
3. **First start ever:** J.A.R.V.I.S says "Guten Tag Sir." **Every later start:** "Willkommen zurück Sir."
4. Closing the window does **not** quit: J.A.R.V.I.S keeps listening in the background and an **orange/blue circle** sits in the system tray (click the `^` arrow next to the clock, drag it out to pin it). Click the circle = GUI opens. Right-click -> Quit to exit really.

## 3. Keys and voice (SETTINGS)
* **Gemini API Key** - https://aistudio.google.com/apikey . Model default `gemini-flash-latest` (change in SETTINGS if you want another).
* **Voice default: Edge TTS, `de-DE-KillianNeural`** (free, needs internet, no key).
* **ElevenLabs:** choose "ElevenLabs" as voice provider, paste API key + Voice-ID. If it fails (wrong key, free plan cannot use a library voice, no credits) the real error is shown in the log window and J.A.R.V.I.S falls back to Edge, then to the offline Windows voice.
* Fish Audio is optional (key + Voice-ID).
* Keys are stored in the Windows Credential Manager, never in the source code and never in the log. `.env` is optional (see `.env.example`).
* Microphone / speaker: pick the device in SETTINGS -> AUDIO. If J.A.R.V.I.S does not react, raise sensitivity (lower "Mikrofon-Schwelle") and check Windows -> Privacy -> Microphone.

### If microphone or speaker are not found
1. SETTINGS -> **AUDIO DIAGNOSE** lists every device Windows reports, tests the microphone and speaker, plays a short test tone and tells you what is wrong. J.A.R.V.I.S now tries other devices, sample rates (16/24/44.1/48 kHz) and mono/stereo automatically, so a stored device that disappeared no longer blocks it.
2. Windows -> Settings -> Privacy & security -> Microphone: *Microphone access* ON and *Let desktop apps access your microphone* ON (the most common reason).
3. Run `pip install -r requirements.txt` again (it now includes `soundfile`, needed to play MP3 voices).
4. Send me the text of the diagnose box if it still fails.

### Settings are remembered
Everything is stored in `C:\jarvis\data\settings.json`. API keys and passwords are stored encrypted (Windows DPAPI) in `C:\jarvis\data\secrets.dat`. After SAVE the status line shows the saved path, and a failed save is shown as an error. A saved microphone/speaker stays selected even if the device is unplugged at that moment.

## 4. How to talk to it
Say "Hey J.A.R.V.I.S ..." , clap twice, or click the reactor / MIC button. Typing in the box under the reactor works too (useful for testing without a microphone).
* "Öffne Discord / Steam / Visual Studio Code / Chrome" - "Öffne meinen Downloads-Ordner" - "Öffne den Desktop"
* "Suche im Internet nach dem Wetter in Kiel" (Gemini with live Google search; browser fallback)
* "Mach lauter", "Nächster Titel", "Mach einen Screenshot", "Wie spät ist es"
* "Merk dir, dass ich morgens Kaffee trinke" / "Vergiss Kaffee"
* Anything else goes to Gemini (math, questions, chat). Gemini only returns *intents*; the local whitelist engine decides what runs. No free shell commands.
* Deleting files / mails and **sending mails always asks first** ("Soll ich ...?" -> say "ja" or "nein").

## 5. E-mail (full assistant control with confirmation)
Commands: "Wie viele ungelesene Mails habe ich?", "Lies die erste Mail", "Fasse meine Mails zusammen", "Räum mein Postfach auf" (finds ads/newsletters, asks, moves them to trash), "Lösche die zweite Mail", "Suche in meinen Mails nach Amazon", "Schreibe eine Mail an Max und sag ihm dass ich später komme" (drafts, reads it back, sends only after "ja").
* **Outlook / Hotmail / Microsoft:** Microsoft no longer allows password login, so you connect once with the browser (OAuth). You need a free Azure app registration:
  1. https://entra.microsoft.com -> App registrations -> New registration.
  2. Supported account types: *any organizational directory and personal Microsoft accounts*.
  3. Redirect URI: platform **Mobile and desktop applications**, `http://localhost`.
  4. API permissions -> Microsoft Graph -> Delegated: `Mail.ReadWrite`, `Mail.Send`.
  5. Copy the *Application (client) ID* into SETTINGS -> "Azure Client-ID", press **MIT OUTLOOK VERBINDEN**.
* **Gmail:** 2-step verification on, create an *App password*, enter address + app password, provider "Gmail".
* **Other IMAP:** set provider "Anderes IMAP", fill IMAP/SMTP server + app password.

## 6. Learning and BRAIN
J.A.R.V.I.S stores lasting facts (preferences, apps it had to search for, mail rules, contacts) in `C:\jarvis\data\memory.db`. After longer messages Gemini extracts facts automatically; "Merk dir ..." stores explicitly. The BRAIN tab shows the nodes, new ones pop in, you can search and press VERGESSEN. Switch off in SETTINGS -> "Aus Gesprächen lernen".

## 7. Phone / SMS (optional, Twilio)
Enter Twilio SID, token, your Twilio number and **your** phone number, then enable PHONE_CALL / SMS under BERECHTIGUNGEN (off by default). "Ruf mich an" / "Ruf mich in 10 Minuten an" calls only your own (or explicitly allowed) numbers, daily limit, call history in `C:\jarvis\data\call_history.json`. J.A.R.V.I.S calls, speaks the message and hangs up - a two-way phone conversation needs a public web server and is not included.

## 8. Safety
Every capability has its own switch (SETTINGS -> BERECHTIGUNGEN). **EMERGENCY STOP** (top right) blocks all actions instantly. Every external action is written to `C:\jarvis\logs\audit.log`; general log: `C:\jarvis\logs\jarvis.log`.

## 9. Build the EXE
```
build_exe.bat
```
Result: `dist\JARVIS\JARVIS.exe` (assets are bundled, paths resolved via PyInstaller). Data stays in `C:\jarvis`.

## 10. Not included yet
Mobile app, banking, smart home, webcam / hand tracking, stock research and trading, two-way phone calls. The permission and module structure is ready for them; they were left out on purpose instead of shipping fake code.

## Privacy note
Wake-word listening uses the free Google speech recognition on short speech snippets. Don't want that? Turn the wake word off in SETTINGS and use clapping or the MIC button.
