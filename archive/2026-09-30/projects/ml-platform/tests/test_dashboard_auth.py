import base64
import json

import pytest

dashboard = pytest.importorskip("dashboard.app")


def _request(headers: dict[str, str]):
    encoded_headers = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return dashboard.Request({"type": "http", "headers": encoded_headers})


def _principal_header(*, name: str, groups: list[str]) -> str:
    claims = [{"typ": "preferred_username", "val": name}]
    claims.extend({"typ": "groups", "val": group} for group in groups)
    payload = json.dumps({"auth_typ": "aad", "claims": claims}).encode()
    return base64.b64encode(payload).decode()


def test_easy_auth_principal_decodes_name_and_groups() -> None:
    principal = dashboard._decode_principal_header(
        _principal_header(name="operator@example.com", groups=["operators"])
    )

    assert principal.name == "operator@example.com"
    assert principal.groups == frozenset({"operators"})


def test_aca_arguments_are_allowlisted() -> None:
    assert dashboard._arguments_for("eval", {"version": "7", "max_rmse": 0.7}) == [
        "--version",
        "7",
        "--max-rmse",
        "0.7",
    ]

    with pytest.raises(RuntimeError, match="Unsupported parameters"):
        dashboard._arguments_for("train", {"shell": "unsafe"})


def test_operator_group_can_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dashboard, "_TRIGGER_BACKEND", "aca")
    monkeypatch.setattr(dashboard, "_OPERATOR_GROUP_ID", "operators")
    request = _request(
        {
            "X-MS-CLIENT-PRINCIPAL": _principal_header(
                name="operator@example.com", groups=["operators"]
            )
        }
    )

    assert dashboard._require_operator(request) == "operator@example.com"


def test_authenticated_viewer_cannot_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dashboard, "_TRIGGER_BACKEND", "aca")
    monkeypatch.setattr(dashboard, "_OPERATOR_GROUP_ID", "operators")
    request = _request(
        {"X-MS-CLIENT-PRINCIPAL": _principal_header(name="viewer@example.com", groups=["viewers"])}
    )

    with pytest.raises(dashboard.HTTPException) as exc_info:
        dashboard._require_operator(request)
    assert exc_info.value.status_code == 403
