"""Creation-time OpenJarvis adapter; never stores tokens or personality in voices."""

from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import urlsplit

import httpx

LIMITS = {
    "display_name": 100,
    "character_name": 150,
    "source": 200,
    "era": 100,
    "version_notes": 1000,
}
MAX_RESPONSE = 128 * 1024


def character_metadata(values):
    """Explicit UI metadata only: never derive identity from a voice name."""
    if not values:  # Preserve existing programmatic voice-only save callers.
        return None, ""
    if len(values) != 9:
        raise ValueError("Complete the Character Personality fields")
    display, kind, name, source, era, notes, conversations, announcements, token = (
        values
    )
    if kind not in ("movie_tv", "literary", "historical", "custom"):
        raise ValueError("Select a supported character type")
    identity = dict(
        display_name=display,
        profile_type=kind,
        character_name=name,
        source=source,
        era=era,
        version_notes=notes,
        conversations=conversations,
        announcements=announcements,
    )
    for key, limit in LIMITS.items():
        value = identity[key]
        if not isinstance(value, str):
            raise ValueError("Complete the Character Personality fields")
        value = value.strip()
        if len(value) > limit or (key != "version_notes" and not value):
            raise ValueError(
                "Complete the Character Personality fields within their limits"
            )
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Invalid character text")
        identity[key] = value
    if not isinstance(conversations, bool) or not isinstance(announcements, bool):
        raise ValueError("Invalid character options")
    if not isinstance(token, str) or not token.strip() or len(token) > 512:
        raise ValueError("Enter the OpenJarvis administrator API key")
    token = token.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in token):
        raise ValueError("Invalid administrator API key")
    return identity, token


def _origin():
    # Configuration is server-owned, never supplied by UI/research content.
    base = os.environ.get("OPENJARVIS_CHARACTER_URL", "http://127.0.0.1:8000").rstrip(
        "/"
    )
    parsed = urlsplit(base)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path
    ):
        raise ValueError("Invalid OpenJarvis integration configuration")
    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise ValueError("Use HTTPS or loopback for administrator authentication")
    return base


def register_character(profile_id, identity, token):
    """One bounded request after successful voice save; no retries or activation."""
    if identity is None:
        return (
            "Set up its pending character in OpenJarvis Device Manager → Voice Routing."
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", profile_id):
        return (
            "Voice saved. Its identifier is unsupported by OpenJarvis; "
            "review it manually."
        )
    body = {**identity, "voice_id": f"clone:{profile_id}"}
    try:
        deadline = time.monotonic() + 315
        with httpx.Client(
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(315, connect=5, write=10, pool=5),
        ) as client:
            with client.stream(
                "POST",
                _origin() + "/api/jarvis/characters",
                headers={"Authorization": "Bearer " + token},
                json=body,
            ) as response:
                if response.status_code in (401, 403):
                    return (
                        "Voice saved. Character setup needs a valid OpenJarvis "
                        "administrator API key."
                    )
                if response.status_code == 409:
                    return (
                        "Voice saved. A character link already exists; review it in "
                        "OpenJarvis Voice Routing."
                    )
                if response.status_code != 200:
                    return (
                        "Voice saved. Character setup is incomplete; continue in "
                        "OpenJarvis Voice Routing."
                    )
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE or time.monotonic() >= deadline:
                        raise ValueError("Character response exceeds limits")
                    chunks.append(chunk)
                result = json.loads(b"".join(chunks))
                if not isinstance(result, dict):
                    raise ValueError("Invalid character response")
                draft = result.get("draft")
                if (
                    result.get("research_error")
                    or not isinstance(draft, dict)
                    or not isinstance(draft.get("payload"), dict)
                    or not draft["payload"].get("traits")
                ):
                    return (
                        "Voice saved. Initial research is incomplete; review the "
                        "pending draft in OpenJarvis Voice Routing and retry "
                        "explicitly."
                    )
                return (
                    "Character draft prepared. Review and approve it in OpenJarvis "
                    "Device Manager → Voice Routing. Personality is not active yet."
                )
    except (httpx.HTTPError, ValueError, OSError):
        # Never echo server pages, engine errors, URLs, credentials, or user text.
        return (
            "Voice saved. OpenJarvis character setup could not be "
            "confirmed; check Voice Routing before retrying."
        )
