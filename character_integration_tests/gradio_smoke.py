"""Run with the deployed Gradio interpreter; no models or real network calls."""

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gradio as gr  # noqa: E402
import gradio_voice_studio as studio  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def main():
    with TemporaryDirectory(prefix="qwen-gradio-smoke-") as directory:
        library = Path(directory)
        blocks = studio.build_app("http://127.0.0.1:8020", library)
        labels = {
            component.get("props", {}).get("label")
            for component in blocks.config["components"]
        }
        assert "Character display name" in labels
        assert "OpenJarvis administrator API key" in labels
        functions = {
            function.fn.__name__: function.fn for function in blocks.fns.values()
        }
        assert all(
            name in functions
            for name in (
                "on_save_preset",
                "on_save_design_as_clone",
                "on_save_clone_profile",
            )
        )
        # The helper is mocked here; real OpenJarvis authorization, storage and
        # approval are covered by the separate cross-repository acceptance test.
        calls = []
        studio.register_character = lambda *args: (
            calls.append(args) or "Voice saved. Research incomplete."
        )
        audio = library / "reference.wav"
        audio.write_bytes(b"mock audio")
        result = functions["on_save_clone_profile"](
            str(library),
            "Atlas",
            "Auto",
            str(audio),
            "Reference",
            False,
            "Atlas",
            "custom",
            "Atlas",
            "Calm guide",
            "Original",
            "",
            True,
            False,
            "test-administrator-key",
        )
        assert "Research incomplete" in result and len(calls) == 1
        metadata = json.loads((library / "profiles/atlas/meta.json").read_text())
        assert "test-administrator-key" not in json.dumps(metadata)
        assert "traits" not in metadata
        app = gr.mount_gradio_app(FastAPI(), blocks, path="/voice-studio")
        with TestClient(app) as client:
            response = client.get("/voice-studio/")
            assert response.status_code == 200
            assert "test-administrator-key" not in response.text
            config = client.get("/voice-studio/config")
            assert config.status_code == 200
            assert len(config.json()["dependencies"]) == 15
        print(
            f"Gradio {gr.__version__}: UI build, save callback and mounted page passed"
        )


if __name__ == "__main__":
    main()
