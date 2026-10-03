"""Learning Companion, the phone app (Flet 1.x).

First build: the phone test. It checks on a real Android phone the three things
the plan depends on (a photo taken and kept, a reminder that fires with the app
closed, sessions that work offline and survive a restart) and runs both use
cases on sample content with the real engine:

* Today: missions to choose from; a session runs card by card.
* Capture: photograph a lesson; the photo stays on the phone (reading it comes
  with the family server).
* Phone test: the three checks, with their status.
* Settings: who is learning, sessions per day, reminder wording.

All the logic is in companion/ (tested without the UI); this file is screens only.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path

import flet as ft

from companion.companion import Companion, Feedback, Prompt, Run
from companion.store import Store, data_dir
from lc_engine import Suggestion, defaults_for_age, reminder_text

INK = "#2F4B7C"
PAPER = "#FAF8F3"
SOLID = "#2E7D5B"
FRAGILE = "#B5542C"
MUTED = "#6B6B6B"

KIND_LABEL = {"by-heart": "By heart", "pushed": "Pushed notion", "test": "Test", "topic": "Topic", "mixed": "Mixed review"}
TEST_REMINDER_ID = 1001
DAILY_REMINDER_ID = 1002


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def hhmm(dt: datetime | None) -> str:
    return dt.strftime("%H:%M") if dt else ""


def heading(text: str) -> ft.Text:
    return ft.Text(text, size=22, weight=ft.FontWeight.BOLD, color=INK)


def small(text: str, color: str = MUTED) -> ft.Text:
    return ft.Text(text, size=13, color=color)


def card(*controls: ft.Control, bgcolor: str = ft.Colors.WHITE) -> ft.Container:
    return ft.Container(
        content=ft.Column(list(controls), spacing=8),
        padding=16,
        border_radius=16,
        bgcolor=bgcolor,
        border=ft.Border.all(1, "#E3DED3"),
    )


class App:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.mobile = page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
        self.android = page.platform == ft.PagePlatform.ANDROID
        self.store = Store()
        self.companion = self._companion()
        self.run: Run | None = None
        self.prompt: Prompt | None = None
        self.phase = "answer"
        self.shown_at = 0.0
        self.feedback: Feedback | None = None
        self.answer_field: ft.TextField | None = None
        self.camera = None
        self.camera_ready = False
        self.notifications = None
        self.reminder_status = ""
        self.body = ft.Container(expand=True, padding=ft.Padding.symmetric(horizontal=16, vertical=12))
        self.tabs = [self.today, self.capture, self.checks, self.settings]

    def _companion(self) -> Companion:
        return Companion(self.store, age=int(self.store.get("age", "12")), tz=self.store.get("tz", "Europe/Paris"))

    def mount(self) -> None:
        page = self.page
        page.title = "Learning Companion"
        page.bgcolor = PAPER
        page.theme = ft.Theme(color_scheme_seed=INK)
        page.navigation_bar = ft.NavigationBar(
            selected_index=0,
            on_change=self.on_tab,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.TODAY_OUTLINED, selected_icon=ft.Icons.TODAY, label="Today"),
                ft.NavigationBarDestination(
                    icon=ft.Icons.CAMERA_ALT_OUTLINED, selected_icon=ft.Icons.CAMERA_ALT, label="Capture"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.FACT_CHECK_OUTLINED, selected_icon=ft.Icons.FACT_CHECK, label="Phone test"
                ),
                ft.NavigationBarDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label="Settings"),
            ],
        )
        page.add(ft.SafeArea(content=self.body, expand=True))
        self.show(0)

    def show(self, index: int) -> None:
        self.page.navigation_bar.selected_index = index
        self.body.content = self.tabs[index]()

    def on_tab(self, e: ft.Event[ft.NavigationBar]) -> None:
        if self.run is not None and self.run.done is None:
            self.run.stop()  # leaving a session ends it kindly; everything left moves to another time
            self.run.next()
            self.run = None
        self.show(e.control.selected_index or 0)

    # ------------------------------------------------------------------ Today

    def today(self) -> ft.Control:
        c = self.companion
        gate = c.gate()
        name = c.learner.name
        done = c.sessions_today()
        status = f"{done} of {c.learner.sessions_per_day} sessions today"
        if not gate.open:
            status += f" · {gate.reason} Next: {hhmm(gate.next_at)}"
        missions = [self.mission_card(s, gate.open) for s in c.suggestions()]
        nxt = c.next_useful()
        footer = small("Short, finite sessions. No streaks, nothing to lose. You can stop any time.")
        return ft.Column(
            [
                heading(f"Hello {name}"),
                small(status, INK if gate.open else FRAGILE),
                small("Pick what you want to work on:"),
                *missions,
                small(f"Next useful moment: {hhmm(nxt)}" if nxt and nxt > c.now() else ""),
                footer,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def mission_card(self, s: Suggestion, can_start: bool) -> ft.Control:
        p = s.progress
        controls: list[ft.Control] = [
            small(KIND_LABEL.get(s.mission.kind, s.mission.kind).upper(), INK),
            ft.Text(s.mission.title, size=18, weight=ft.FontWeight.W_600),
            small(s.reason),
        ]
        if p.total:
            controls.append(ft.ProgressBar(value=p.secure / p.total, bar_height=6, color=SOLID, bgcolor="#E8E4DA"))
        controls.append(
            ft.FilledButton(
                content="Start",
                icon=ft.Icons.PLAY_ARROW,
                disabled=not can_start,
                data=s.mission.id,
                on_click=lambda e, mid=s.mission.id: self.start(mid),
            )
        )
        return card(*controls)

    # ------------------------------------------------------------------ a session

    def start(self, mission_id: str) -> None:
        run = self.companion.start(mission_id)
        if run.empty:
            run.finish()
            nxt = self.companion.next_useful()
            self.toast(
                f"Nothing useful in this mission right now. Come back at {hhmm(nxt)}." if nxt else "Nothing to do here yet."
            )
            return
        self.run = run
        self.advance()

    def advance(self) -> None:
        assert self.run is not None
        self.prompt = self.run.next()
        self.feedback = None
        if self.prompt is None:
            self.phase = "done"
        else:
            self.phase = "study" if self.prompt.study_text else "answer"
            self.shown_at = time.monotonic()
        self.body.content = self.session_view()

    def session_view(self) -> ft.Control:
        run, prompt = self.run, self.prompt
        assert run is not None
        if self.phase == "done":
            return self.done_view()
        assert prompt is not None
        top = ft.Row(
            [
                ft.Column([small(run.mission.title, INK), small(prompt.position)], spacing=0, expand=True),
                ft.TextButton(content="Stop", icon=ft.Icons.STOP_CIRCLE_OUTLINED, on_click=self.stop),
            ]
        )
        parts: list[ft.Control] = [top, ft.Text(prompt.title, size=18, weight=ft.FontWeight.W_600)]
        if prompt.retry:
            parts.append(small("Second try: this one helps, it does not count against you."))
        if self.phase == "study":
            parts += [
                small("Read it slowly, out loud if you can."),
                card(ft.Text(prompt.study_text, size=20, font_family="serif", selectable=True)),
                ft.FilledButton(content="I've read it: hide it", icon=ft.Icons.VISIBILITY_OFF, on_click=self.to_answer),
            ]
        elif self.phase == "answer":
            parts += self.answer_controls(prompt)
        else:
            parts += self.feedback_controls()
        return ft.Column(
            parts, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )

    def to_answer(self, e: ft.Event[ft.FilledButton]) -> None:
        self.phase = "answer"
        self.shown_at = time.monotonic()
        self.body.content = self.session_view()

    def answer_controls(self, prompt: Prompt) -> list[ft.Control]:
        if prompt.cue_text is not None:
            hint = {
                "first-letters": "Recite it. The first letters are there to help.",
                "key-words-blank": "Recite it. The key words are hidden.",
                "recite": "Recite it from memory.",
            }.get(prompt.cue_level or "", "Recite it.")
            self.answer_field = ft.TextField(
                label="Your recitation", multiline=True, min_lines=4, autofocus=True, autocorrect=False
            )
            return [
                small(hint),
                card(ft.Text(prompt.cue_text, size=16, font_family="monospace")),
                self.answer_field,
                ft.FilledButton(content="Check", icon=ft.Icons.CHECK, on_click=self.check),
            ]
        q = prompt.question
        assert q is not None
        controls: list[ft.Control] = [card(ft.Text(q.prompt, size=22, weight=ft.FontWeight.W_500))]
        if q.choices:
            controls += [ft.OutlinedButton(content=choice, on_click=lambda e, c=choice: self.submit(c)) for choice in q.choices]
        else:
            self.answer_field = ft.TextField(label="Your answer", autofocus=True, autocorrect=False, on_submit=self.check)
            controls += [self.answer_field, ft.FilledButton(content="Check", icon=ft.Icons.CHECK, on_click=self.check)]
        return controls

    def check(self, e: ft.Event[ft.Control]) -> None:
        self.submit(self.answer_field.value if self.answer_field else "")

    def submit(self, given: str | None) -> None:
        assert self.run is not None
        latency_ms = int((time.monotonic() - self.shown_at) * 1000)
        self.feedback = self.run.answer(given or "", latency_ms=latency_ms, seconds=latency_ms / 1000)
        self.phase = "feedback"
        self.body.content = self.session_view()

    def feedback_controls(self) -> list[ft.Control]:
        f = self.feedback
        assert f is not None
        if f.correct:
            verdict, color = "Right.", SOLID
        elif f.near_miss:
            verdict, color = "Nearly: it comes back soon.", INK
        else:
            verdict, color = "Not yet: it comes back later, with the text to help.", FRAGILE
        controls: list[ft.Control] = [ft.Text(verdict, size=20, weight=ft.FontWeight.BOLD, color=color)]
        if f.missing:
            controls.append(small("Missing or out of order: " + ", ".join(f.missing), FRAGILE))
        if not f.correct:
            controls.append(card(ft.Text(f.expected, size=16, font_family="serif", selectable=True)))
        controls.append(ft.FilledButton(content="Next", icon=ft.Icons.ARROW_FORWARD, on_click=lambda e: self.advance()))
        return controls

    def stop(self, e: ft.Event[ft.TextButton]) -> None:
        assert self.run is not None
        self.run.stop()
        self.advance()

    def done_view(self) -> ft.Control:
        run = self.run
        assert run is not None and run.done is not None
        nxt = self.companion.next_useful()
        lines = [
            heading("Done"),
            ft.Text(run.done.message, size=16),
            small(f"{plural(run.answers, 'answer')}, {run.correct} right."),
        ]
        if nxt and nxt > self.companion.now():
            day = "" if nxt.date() == self.companion.now().date() else " tomorrow"
            lines.append(small(f"Next useful moment: {hhmm(nxt)}{day}."))
        lines.append(ft.FilledButton(content="Back to today", on_click=self.back_to_today))
        return ft.Column(lines, spacing=12)

    def back_to_today(self, e: ft.Event[ft.FilledButton]) -> None:
        self.run = None
        self.show(0)

    # ------------------------------------------------------------------ Capture

    def capture(self) -> ft.Control:
        photos = self.store.photos()
        thumbs = [
            ft.Image(src=Path(path).read_bytes(), width=96, height=128, fit=ft.BoxFit.COVER, border_radius=8)
            for path, _, _ in photos[:3]
            if Path(path).exists()
        ]
        controls: list[ft.Control] = [
            heading("Photograph a lesson"),
            small("One photo per page. The photo stays on this phone; reading it into cards comes with the family server."),
        ]
        if not self.mobile:
            controls.append(card(small("The camera works on the phone. Here, the rest of the app works as usual.")))
        else:
            if self.camera is None:
                import flet_camera as fc

                self.camera = fc.Camera(expand=True, preview_enabled=True)
            controls += [
                ft.Container(content=self.camera, height=360, border_radius=16, bgcolor=ft.Colors.BLACK),
                ft.Row(
                    [
                        ft.OutlinedButton(content="Start camera", icon=ft.Icons.CAMERA, on_click=self.start_camera),
                        ft.FilledButton(content="Take photo", icon=ft.Icons.CAMERA_ALT, on_click=self.take_photo),
                    ],
                    wrap=True,
                ),
            ]
        controls += [small(f"{plural(len(photos), 'photo')} kept on this phone"), ft.Row(thumbs, wrap=True)]
        return ft.Column(controls, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

    async def start_camera(self, e: ft.Event[ft.OutlinedButton]) -> None:
        import flet_camera as fc
        import flet_permission_handler as fph

        status = await fph.PermissionHandler().request(fph.Permission.CAMERA)
        if status != fph.PermissionStatus.GRANTED:
            self.toast("The camera needs your permission (Android settings › Apps › Learning Companion).")
            return
        cameras = await self.camera.get_available_cameras()
        if not cameras:
            self.toast("No camera found.")
            return
        back = next((c for c in cameras if c.lens_direction == fc.CameraLensDirection.BACK), cameras[0])
        await self.camera.initialize(
            back, fc.ResolutionPreset.HIGH, enable_audio=False, image_format_group=fc.ImageFormatGroup.JPEG
        )
        self.camera_ready = True

    async def take_photo(self, e: ft.Event[ft.FilledButton]) -> None:
        if not self.camera_ready:
            self.toast("Start the camera first.")
            return
        data = await self.camera.take_picture()
        now = self.companion.now()
        folder = data_dir() / "photos"
        folder.mkdir(exist_ok=True)
        path = folder / f"lesson-{now:%Y%m%d-%H%M%S}.jpg"
        await asyncio.to_thread(path.write_bytes, data)
        self.store.add_photo(str(path), now)
        self.toast("Photo kept on this phone.")
        self.body.content = self.capture()

    # ------------------------------------------------------------------ Phone test

    def checks(self) -> ft.Control:
        photos = len(self.store.photos())
        answers = self.store.review_count(self.companion.learner_id)

        def row(ok: bool, title: str, detail: str) -> ft.Control:
            icon = ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.RADIO_BUTTON_UNCHECKED, color=SOLID if ok else MUTED)
            return ft.Row([icon, ft.Column([ft.Text(title, weight=ft.FontWeight.W_600), small(detail)], spacing=2, expand=True)])

        reminder_controls: list[ft.Control] = [
            row(
                bool(self.reminder_status), "2. A reminder arrives with the app closed", self.reminder_status or "Not tried yet."
            ),
        ]
        if self.android:
            reminder_controls += [
                ft.FilledButton(content="Remind me in 2 minutes", icon=ft.Icons.NOTIFICATIONS, on_click=self.test_reminder),
                small("Then close the app completely (swipe it away from recent apps) and wait."),
                ft.Switch(
                    label=f"Daily reminder at {self.store.get('reminder_time', '17:30')}",
                    value=self.store.get("daily_reminder") == "on",
                    on_change=self.toggle_daily,
                ),
            ]
        else:
            reminder_controls.append(small("Reminders are tested on the Android phone."))
        return ft.Column(
            [
                heading("Phone test"),
                small("Three things to check on this phone before building the rest."),
                card(
                    row(
                        photos > 0,
                        "1. A photo is taken and kept",
                        f"{plural(photos, 'photo')} on this phone." if photos else "Take one in Capture.",
                    ),
                ),
                card(*reminder_controls),
                card(
                    row(
                        answers > 0,
                        "3. Sessions work offline and survive a restart",
                        f"{plural(answers, 'answer')} saved on this phone. Turn on airplane mode, close the app, reopen it: "
                        "the number and your missions are still here.",
                    ),
                    small(f"Stored in {self.store.path}"),
                ),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _notifications(self):
        if self.notifications is None:
            from flet_android_notifications import FletAndroidNotifications

            self.notifications = FletAndroidNotifications()
        return self.notifications

    async def _allowed(self) -> tuple[bool, str]:
        n = self._notifications()
        if not await n.request_permissions():
            self.toast("Notifications are off for this app (Android settings › Notifications).")
            return False, ""
        exact = await n.can_schedule_exact_notifications()
        return True, "exact_allow_while_idle" if exact else "inexact_allow_while_idle"

    async def test_reminder(self, e: ft.Event[ft.FilledButton]) -> None:
        ok, mode = await self._allowed()
        if not ok:
            return
        at = self.companion.now() + timedelta(minutes=2)
        await self._notifications().schedule_notification(
            TEST_REMINDER_ID,
            "Learning Companion",
            "Test reminder: if you can read this with the app closed, check 2 passes.",
            at.replace(tzinfo=None),
            time_zone=self.store.get("tz", "Europe/Paris"),
            schedule_mode=mode,
            channel_id="reminders",
            channel_name="Reminders",
            channel_description="At most one a day, at the time you agreed",
        )
        self.reminder_status = f"Scheduled for {hhmm(at)}" + (
            "" if mode.startswith("exact") else " (Android may deliver it a few minutes late)"
        )
        self.body.content = self.checks()

    async def toggle_daily(self, e: ft.Event[ft.Switch]) -> None:
        n = self._notifications()
        if not e.control.value:
            await n.cancel(DAILY_REMINDER_ID)
            self.store.set("daily_reminder", "off")
            return
        ok, _ = await self._allowed()
        if not ok:
            e.control.value = False
            return
        hour, minute = (int(x) for x in self.store.get("reminder_time", "17:30").split(":"))
        now = self.companion.now()
        first = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if first <= now:
            first += timedelta(days=1)
        plan_minutes = self.companion.learner.session_minutes
        text = reminder_text(self.store.get("intention") or None, int(plan_minutes), ["French"])
        await n.schedule_notification(
            DAILY_REMINDER_ID,
            "Learning Companion",
            text,
            first.replace(tzinfo=None),
            time_zone=self.store.get("tz", "Europe/Paris"),
            match_date_time_components="time",
            channel_id="reminders",
            channel_name="Reminders",
            channel_description="At most one a day, at the time you agreed",
        )
        self.store.set("daily_reminder", "on")
        self.toast(f"One reminder a day at {hhmm(first)}: “{text}”")

    # ------------------------------------------------------------------ Settings

    def settings(self) -> ft.Control:
        name = ft.TextField(label="First name", value=self.store.get("name", "Léa"))
        age = ft.Dropdown(
            label="Age",
            value=self.store.get("age", "12"),
            options=[ft.DropdownOption(key=str(a), text=str(a)) for a in (10, 11, 12, 13)]
            + [ft.DropdownOption(key="40", text="Parent")],
        )
        band = defaults_for_age(int(self.store.get("age", "12")))
        lo, hi = (int(x) for x in band.sessions_per_day_range)
        per_day = ft.Slider(
            min=lo,
            max=hi,
            divisions=hi - lo,
            value=int(self.store.get("sessions_per_day", str(band.sessions_per_day))),
            label="{value} sessions a day",
        )
        intention = ft.TextField(
            label="Reminder starts with (your own words)", value=self.store.get("intention", ""), hint_text="After my snack"
        )
        reminder_time = ft.TextField(label="Reminder time (HH:MM)", value=self.store.get("reminder_time", "17:30"), width=180)

        def save(e: ft.Event[ft.FilledButton]) -> None:
            self.store.set("name", (name.value or "").strip() or "Léa")
            self.store.set("age", age.value or "12")
            self.store.set("sessions_per_day", str(int(per_day.value or 2)))
            self.store.set("intention", (intention.value or "").strip())
            if _valid_time(reminder_time.value or ""):
                self.store.set("reminder_time", reminder_time.value or "17:30")
            self.companion = self._companion()
            self.toast("Saved.")

        return ft.Column(
            [
                heading("Settings"),
                name,
                age,
                small("Sessions per day (each one short, with a break in between)"),
                per_day,
                intention,
                reminder_time,
                ft.FilledButton(content="Save", icon=ft.Icons.SAVE, on_click=save),
                small(f"Data folder: {data_dir()}"),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    # ------------------------------------------------------------------ helpers

    def toast(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message), duration=4000))


def _valid_time(value: str) -> bool:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        return False
    return True


def main(page: ft.Page) -> None:
    App(page).mount()


if __name__ == "__main__":
    ft.run(main)
