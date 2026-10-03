# Phone app (Flet)

The family app in Python, drawn by [Flet](https://flet.dev) (Flutter underneath). This first build is the **phone test**. On a real Android phone it checks the three things the rest of the plan depends on, and it runs both use cases on sample content with the real engine.

| Tab | What to try |
|---|---|
| **Today** | Pick a mission. *Le Corbeau et le Renard* (learn by heart): read a part, hide it, recite it with first letters as help; the cues fade on later days. *Passé simple* (a notion pushed by parents): varied exercises, accents count. A break is required between sessions, and the day has a limit. |
| **Capture** | Photograph a lesson page. The photo stays on the phone; reading it into cards comes with the family server ([`packages/server`](../packages/server)). |
| **Phone test** | The three checks: **1.** a photo is taken and kept; **2.** a reminder arrives with the app closed ("Remind me in 2 minutes", then swipe the app away); **3.** answers survive airplane mode and a restart. |
| **Settings** | First name, age (10–13 or parent), sessions per day within the age limits, the reminder's first words and time. |

## Install it on an Android phone

1. On GitHub, open **Actions › Android APK** and the latest successful run (it builds on every push that touches `app/` or the engine; **Run workflow** starts one by hand).
2. Download the **learning-companion-apk** artifact, unzip it and copy the `.apk` to the phone (USB, Drive, email).
3. Open it on the phone. Android asks once to allow installs from that app (Files, Drive…). Then open *Learning Companion* and go through the **Phone test** tab.

The APK is built for 64-bit ARM phones (nearly every Android phone from the last eight years) and signed with a debug key: fine for the family, not for the Play Store.

## Run it on a computer

```bash
cd app
uv sync
uv run flet run src/main.py        # desktop window; the camera and reminders only work on the phone
uv run pytest                      # app logic + screens, driven headlessly
```

## Build the APK yourself

Needs about 10 GB of disk: Flet downloads Flutter, the JDK and the Android SDK on the first build.

```bash
cd app
uv run python scripts/notifications_template.py   # Flet's template, patched for scheduled reminders
uv run flet build apk --arch arm64-v8a --python-version 3.12
# -> build/apk/*.apk
```

## How it is put together

* `src/main.py`: the screens only.
* `src/companion/`: everything else, tested without the UI. That covers sample content (`content.py`), offline storage in SQLite (`store.py`, an append-only review log from which memory states are rebuilt), and the session flow on top of the engine (`companion.py`).
* The engine ([`packages/engine`](../packages/engine)) is installed from this repository (`[tool.flet.dev_packages]`). Its only dependency, `py-fsrs`, is pure Python, so nothing needs compiling for Android.
* **Reminders** use [`flet-android-notifications`](https://github.com/alex-stoica/flet-android-notifications). It is a community extension (MIT) and the only Flet 1.x package whose reminders fire while the app is closed. It needs Flet's build template patched, which `scripts/notifications_template.py` does. If it ever breaks, the fallback is a push notification from the family server.
* **Time zone:** the app uses the zone set in its settings (Europe/Paris by default). Python's `zoneinfo` gets its data from the `tzdata` package on Android.
