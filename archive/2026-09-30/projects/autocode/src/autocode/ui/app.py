"""Composition root for an optional Flet client."""

from __future__ import annotations

import importlib
from typing import Any

from autocode.state import UIState, reduce


def dispatch(state: UIState, *actions: dict[str, object]) -> UIState:
    for action in actions:
        state = reduce(state, action)
    return state


def run_desktop() -> None:
    try:
        ft: Any = importlib.import_module("flet")
    except ImportError as exc:
        raise RuntimeError("install autocode[desktop] to run the Flet client") from exc

    def view(page: Any) -> None:
        page.title = "autocode"
        state = UIState(session_id="local")
        messages = ft.ListView(expand=True, spacing=8, auto_scroll=True)
        composer = ft.TextField(label="Message", expand=True, autofocus=True)
        session_picker = ft.Dropdown(
            label="Session",
            width=240,
            options=[ft.dropdown.Option("local")],
            value="local",
        )
        status = ft.Text("offline")

        def submit(_event: Any) -> None:
            nonlocal state
            if not composer.value:
                return
            content = composer.value
            state = dispatch(
                state,
                {"type": "draft_changed", "value": content},
                {"type": "message_submitted"},
            )
            messages.controls.append(ft.Text(content, selectable=True))
            composer.value = ""
            page.update()

        composer.on_submit = submit
        page.add(
            ft.Row([session_picker, status]),
            messages,
            ft.Row([composer, ft.ElevatedButton("Send", on_click=submit)]),
        )

    ft.app(target=view)
