"""Drives the real screens headlessly: a Flet session whose messages are encoded
exactly as the socket server would send them, with clicks dispatched as events.

Runs in the app's own environment (uv run --directory app pytest); skipped elsewhere.
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

ft = pytest.importorskip("flet")
msgpack = pytest.importorskip("msgpack")

from flet.controls.base_control import BaseControl  # noqa: E402
from flet.messaging.connection import Connection  # noqa: E402
from flet.messaging.protocol import configure_encode_object_for_msgpack  # noqa: E402
from flet.messaging.session import Session  # noqa: E402
from flet.pubsub.pubsub_hub import PubSubHub  # noqa: E402


class FakeConnection(Connection):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[bytes] = []

    def send_message(self, message) -> None:
        # Encoding every update proves the control tree serializes, as on a phone.
        self.sent.append(msgpack.packb([message.action, message.body], default=configure_encode_object_for_msgpack(BaseControl)))


def new_session() -> tuple[Session, FakeConnection]:
    conn = FakeConnection()
    conn.pubsubhub = PubSubHub()
    conn.loop = asyncio.get_running_loop()
    session = Session(conn)
    from flet.controls.context import _context_page

    _context_page.set(session.page)
    msgpack.packb(session.get_page_patch(), default=configure_encode_object_for_msgpack(BaseControl))
    return session, conn


def walk(control):
    """Every control under ``control``."""
    yield control
    for attr in ("content", "controls", "actions"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                yield from walk(c)
        elif isinstance(child, BaseControl):
            yield from walk(child)


def find(root, cls, text: str | None = None):
    for c in walk(root):
        if isinstance(c, cls) and (text is None or text in str(getattr(c, "content", "") or getattr(c, "value", "") or "")):
            return c
    return None


def start_button(root, mission_id: str):
    return next(c for c in walk(root) if isinstance(c, ft.FilledButton) and c.data == mission_id)


async def click(session: Session, control) -> None:
    assert control is not None, "control not on screen"
    await session.dispatch_event(control._i, "click", None)


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    return importlib.import_module("main")


def test_tabs_render_and_a_by_heart_session_runs(app_module):
    async def go():
        session, conn = new_session()
        page = session.page
        app_module.main(page)
        body = page.controls[0].content
        assert find(body, ft.Text, "Hello Léa") is not None
        assert find(body, ft.Text, "LE CORBEAU") is None  # kind labels are upper case, titles are not
        assert find(body, ft.Text, "Le Corbeau et le Renard") is not None

        # Every tab renders and serializes.
        nav = page.navigation_bar
        for index in (1, 2, 3, 0):
            nav.selected_index = index
            await session.dispatch_event(nav._i, "change", None)
        assert find(body, ft.Text, "Hello") is not None

        await click(session, start_button(body, "by-heart:corbeau"))
        assert find(body, ft.FilledButton, "I've read it") is not None, "first meeting: study the text"
        await click(session, find(body, ft.FilledButton, "I've read it"))

        answered = 0
        while find(body, ft.Text, "Done") is None and answered < 40:
            if find(body, ft.FilledButton, "I've read it"):
                await click(session, find(body, ft.FilledButton, "I've read it"))
                continue
            field = find(body, ft.TextField)
            field.value = "Maître Corbeau, sur un arbre perché"
            await click(session, find(body, ft.FilledButton, "Check"))
            answered += 1
            assert find(body, ft.FilledButton, "Next") is not None
            await click(session, find(body, ft.FilledButton, "Next"))
        assert find(body, ft.Text, "Done") is not None
        assert answered > 0
        await click(session, find(body, ft.FilledButton, "Back to today"))
        assert find(body, ft.Text, "1 of 2 sessions today") is not None
        assert len(conn.sent) > 5

    asyncio.run(go())


def test_pushed_notion_practice_with_choices_and_typed_answers(app_module):
    async def go():
        session, _ = new_session()
        page = session.page
        app_module.main(page)
        body = page.controls[0].content
        await click(session, start_button(body, "pushed:passe-simple"))
        steps = 0
        while find(body, ft.Text, "Done") is None and steps < 30:
            choice = find(body, ft.OutlinedButton)
            if choice is not None:
                await click(session, choice)
            else:
                find(body, ft.TextField).value = "chantèrent"
                await click(session, find(body, ft.FilledButton, "Check"))
            await click(session, find(body, ft.FilledButton, "Next"))
            steps += 1
        assert find(body, ft.Text, "Done") is not None

    asyncio.run(go())


def test_settings_save_and_phone_test_checklist(app_module):
    async def go():
        session, _ = new_session()
        page = session.page
        app_module.main(page)
        body = page.controls[0].content
        nav = page.navigation_bar
        nav.selected_index = 3
        await session.dispatch_event(nav._i, "change", None)
        find(body, ft.TextField).value = "Tom"
        await click(session, find(body, ft.FilledButton, "Save"))
        nav.selected_index = 2
        await session.dispatch_event(nav._i, "change", None)
        assert find(body, ft.Text, "1. A photo is taken and kept") is not None
        assert find(body, ft.Text, "Reminders are tested on the Android phone.") is not None
        nav.selected_index = 0
        await session.dispatch_event(nav._i, "change", None)
        assert find(body, ft.Text, "Hello Tom") is not None

    asyncio.run(go())


def test_on_android_the_camera_and_reminder_controls_render(app_module):
    async def go():
        session, _ = new_session()
        page = session.page
        page.platform = ft.PagePlatform.ANDROID
        app_module.main(page)
        body = page.controls[0].content
        nav = page.navigation_bar
        nav.selected_index = 1
        await session.dispatch_event(nav._i, "change", None)
        import flet_camera as fc

        assert find(body, fc.Camera) is not None
        assert find(body, ft.FilledButton, "Take photo") is not None
        nav.selected_index = 2
        await session.dispatch_event(nav._i, "change", None)
        assert find(body, ft.FilledButton, "Remind me in 2 minutes") is not None
        assert find(body, ft.Switch) is not None

    asyncio.run(go())
