"""Offline tests: no model download, research network, or production services."""

import importlib.util
import inspect
import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import openjarvis_characters as adapter  # noqa: E402


@pytest.fixture
def fields():
    return [
        "Atlas",
        "custom",
        "Atlas",
        "Calm guide",
        "Original",
        "",
        True,
        False,
        "test-administrator-key",
    ]


@pytest.mark.parametrize("kind", ["movie_tv", "literary", "historical", "custom"])
def test_explicit_identity_and_separate_authentication(fields, kind):
    fields[1] = kind
    identity, token = adapter.character_metadata(fields)
    assert identity["character_name"] == "Atlas"
    assert identity["profile_type"] == kind
    assert "voice_id" not in identity and "token" not in identity
    assert token == "test-administrator-key"


@pytest.mark.parametrize(
    "index,value",
    [
        (0, ""),
        (1, "unknown"),
        (2, ""),
        (3, "x" * 201),
        (4, ""),
        (6, "yes"),
        (8, ""),
        (8, "key\nattack"),
    ],
)
def test_invalid_metadata_rejected_before_voice_save(fields, index, value):
    fields[index] = value
    with pytest.raises(ValueError):
        adapter.character_metadata(fields)


def mock_transport(monkeypatch, handler):
    actual_client = httpx.Client
    monkeypatch.setattr(
        adapter.httpx,
        "Client",
        lambda **kwargs: actual_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )


def test_single_authenticated_initial_request_never_approves(monkeypatch, fields):
    identity, token = adapter.character_metadata(fields)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/jarvis/characters"
        assert request.headers["authorization"] == "Bearer " + token
        body = json.loads(request.content)
        assert body["voice_id"] == "clone:unrelated-voice-id"
        assert body["character_name"] == "Atlas"
        assert token not in request.content.decode()
        return httpx.Response(
            200, json={"draft": {"payload": {"traits": {"tone": "Calm"}}}}
        )

    mock_transport(monkeypatch, handler)
    result = adapter.register_character("unrelated-voice-id", identity, token)
    assert "Review and approve" in result and "not active yet" in result
    assert len(calls) == 1


@pytest.mark.parametrize("status", [401, 403, 409, 429, 500])
def test_backend_failures_preserve_voice_and_do_not_retry(monkeypatch, fields, status):
    identity, token = adapter.character_metadata(fields)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="PRIVATE_SERVICE_ERROR " + token)

    mock_transport(monkeypatch, handler)
    result = adapter.register_character("atlas", identity, token)
    assert "Voice saved" in result
    assert token not in result and "PRIVATE_SERVICE_ERROR" not in result
    assert len(calls) == 1


def test_incomplete_initial_research_is_recoverable(monkeypatch, fields):
    identity, token = adapter.character_metadata(fields)
    mock_transport(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json={
                "research_error": "incomplete",
                "draft": {"payload": {"traits": None}},
            },
        ),
    )
    result = adapter.register_character("atlas", identity, token)
    assert "pending draft" in result and "retry explicitly" in result


def test_response_limit_and_network_failure_are_safe(monkeypatch, fields):
    identity, token = adapter.character_metadata(fields)
    mock_transport(
        monkeypatch,
        lambda _: httpx.Response(200, content=b"x" * (adapter.MAX_RESPONSE + 1)),
    )
    assert "could not be confirmed" in adapter.register_character(
        "atlas", identity, token
    )


def test_trusted_configuration_cannot_redirect_credentials(monkeypatch, fields):
    identity, token = adapter.character_metadata(fields)
    calls = []
    mock_transport(
        monkeypatch,
        lambda request: (
            calls.append(request)
            or httpx.Response(302, headers={"Location": "https://example.org/capture"})
        ),
    )
    assert "incomplete" in adapter.register_character("atlas", identity, token)
    assert len(calls) == 1
    monkeypatch.setenv("OPENJARVIS_CHARACTER_URL", "http://10.5.1.60:8000")
    assert "could not be confirmed" in adapter.register_character(
        "atlas", identity, token
    )
    assert len(calls) == 1


def studio_module(monkeypatch):
    """Exercise real save callbacks without loading Gradio/model dependencies."""
    callbacks = {}

    class Component:
        def __init__(self, *args, **kwargs):
            self.value = kwargs.get("value")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def click(self, fn, inputs=None, outputs=None, **kwargs):
            inspect.signature(fn).bind(*([None] * len(inputs or [])))
            callbacks[fn.__name__] = fn
            return self

        def then(self, *args, **kwargs):
            return self

        def load(self, *args, **kwargs):
            return self

    gradio = types.ModuleType("gradio")
    gradio.Error = ValueError
    gradio.themes = types.SimpleNamespace(Soft=Component)
    for name in (
        "Blocks",
        "State",
        "HTML",
        "Accordion",
        "Row",
        "Textbox",
        "Number",
        "Button",
        "Markdown",
        "Tabs",
        "Tab",
        "Column",
        "Dropdown",
        "Audio",
        "File",
        "Checkbox",
        "Dataframe",
        "JSON",
        "Slider",
    ):
        setattr(gradio, name, Component)
    monkeypatch.setitem(sys.modules, "gradio", gradio)
    spec = importlib.util.spec_from_file_location(
        "studio_test", ROOT / "gradio_voice_studio.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "studio_test", module)
    spec.loader.exec_module(module)
    return module, callbacks


@pytest.mark.parametrize("save", ["preset", "design", "clone"])
def test_ui_save_callbacks_preserve_voice_and_keep_character_separate(
    tmp_path, monkeypatch, fields, save
):
    studio, callbacks = studio_module(monkeypatch)
    studio.build_app("http://localhost:8880", tmp_path)
    registration = Mock(return_value="Voice saved. Research incomplete.")
    monkeypatch.setattr(studio, "register_character", registration)
    audio = tmp_path / "reference.wav"
    audio.write_bytes(b"mock audio")
    if save == "preset":
        result = callbacks["on_save_preset"](
            str(tmp_path), "Atlas", "Vivian", "Auto", "", *fields
        )
    elif save == "design":
        result = callbacks["on_save_design_as_clone"](
            str(tmp_path), "Atlas", "Auto", "Calm", "Reference", str(audio), *fields
        )
    else:
        result = callbacks["on_save_clone_profile"](
            str(tmp_path), "Atlas", "Auto", str(audio), "Reference", False, *fields
        )
    metadata = json.loads((tmp_path / "profiles/atlas/meta.json").read_text())
    assert "Research incomplete" in result
    assert "character_name" not in metadata and "traits" not in metadata
    assert fields[-1] not in json.dumps(metadata)
    assert registration.call_args.args[1]["character_name"] == "Atlas"
    if save != "preset":
        assert (tmp_path / "profiles/atlas/atlas.wav").exists()


def test_ui_validation_and_legacy_save_compatibility(tmp_path, monkeypatch, fields):
    studio, callbacks = studio_module(monkeypatch)
    studio.build_app("http://localhost:8880", tmp_path)
    fields[2] = ""
    with pytest.raises(ValueError):
        callbacks["on_save_preset"](
            str(tmp_path), "Atlas", "Vivian", "Auto", "", *fields
        )
    assert not (tmp_path / "profiles/atlas").exists()
    result = callbacks["on_save_preset"](str(tmp_path), "Atlas", "Vivian", "Auto", "")
    assert "Voice Routing" in result
    with pytest.raises(ValueError):
        studio.named_profile_id("a" * 81)


def test_studio_to_openjarvis_creation_and_approval(tmp_path, monkeypatch, fields):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.characters import research, voices
    from openjarvis.characters.models import Identity, Revision, Traits
    from openjarvis.characters.runtime import resolve
    from openjarvis.characters.store import Store
    from openjarvis.server.character_routes import router

    studio, callbacks = studio_module(monkeypatch)
    library = tmp_path / "voices"
    studio.build_app("http://localhost:8880", library)
    monkeypatch.setattr(voices, "VOICE_ROOT", library / "profiles")
    app = FastAPI()
    app.include_router(router)
    app.state.api_key = fields[-1]
    app.state.character_store = Store(tmp_path / "characters.db")
    app.state.engine = Mock()
    app.state.model = "configured-model"
    identity, token = adapter.character_metadata(fields)
    revision = Revision(
        identity=Identity(**identity, voice_id="clone:atlas"),
        traits=Traits(**{name: "Calm and concise." for name in Traits.model_fields}),
    )
    research_calls = Mock(return_value=revision)
    monkeypatch.setattr(research, "research", research_calls)
    service = TestClient(app)

    def handler(request):
        response = service.post(
            request.url.path,
            content=request.content,
            headers={
                "Authorization": request.headers["Authorization"],
                "Content-Type": "application/json",
            },
        )
        return httpx.Response(response.status_code, content=response.content)

    mock_transport(monkeypatch, handler)
    audio = tmp_path / "reference.wav"
    audio.write_bytes(b"mock audio")
    result = callbacks["on_save_clone_profile"](
        str(library), "Atlas", "Auto", str(audio), "Reference", False, *fields
    )
    assert "Review and approve" in result
    profile = app.state.character_store.list()[0]
    assert profile["approved"] is None and profile["draft"]["payload"]["traits"]
    app.state.character_store.select_voice("clone:atlas")
    assert not resolve(app.state.character_store).style
    response = service.post(
        f"/api/jarvis/characters/{profile['id']}/action",
        headers={"Authorization": "Bearer " + token},
        json={"generation": profile["generation"], "action": "approve"},
    )
    assert response.status_code == 200
    assert resolve(app.state.character_store).style
    assert research_calls.call_count == 1
    app.state.character_store.mutate(
        profile["id"], response.json()["generation"], "remove"
    )
    assert not resolve(app.state.character_store).style
    assert (library / "profiles/atlas/atlas.wav").exists()
