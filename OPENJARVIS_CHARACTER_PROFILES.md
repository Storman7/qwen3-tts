# OpenJarvis Character Profiles

Voice Studio can prepare a Character Profile when a new preset, designed clone,
or reference-audio clone is saved. Voice assets remain in the Qwen library;
identity, personality drafts, sources, revisions and approvals remain in the
OpenJarvis user-data database.

## Configuration

Run alongside OpenJarvis with its existing administrator API key configured.
The adapter defaults to `http://127.0.0.1:8000`. If needed, set the server-owned
`OPENJARVIS_CHARACTER_URL` environment variable to the OpenJarvis origin.
HTTP is allowed only for loopback; a separate host requires HTTPS. Redirects
and environment proxies are disabled. The integration destination cannot be
changed through Voice Studio form fields or researched material.

Enter the OpenJarvis API key in the masked creation form for each session.
It is sent as a Bearer header and is never saved in voice metadata or source.
The studio must be served through your trusted authenticated interface; use
HTTPS when accessed over the network. The existing API key represents the
OpenJarvis administrator, so do not share it with ordinary household clients.

## Creating a voice

1. Enter explicit character metadata in Character Personality — initial setup.
   Custom profiles use an original character name and a research brief.
2. Save the voice. Metadata is validated before writing it. OpenJarvis is
   contacted only after the voice has been saved successfully.
3. Wait for the bounded initial research request, which can take five minutes.
4. Review and approve the draft in OpenJarvis Device Manager → Voice Routing.
   The studio never approves, activates or selects the personality.

If OpenJarvis is unavailable, credentials are invalid, or research is incomplete,
the saved voice remains intact and neutral. Check Voice Routing for an existing
pending draft before explicitly retrying; the adapter never retries automatically.
An existing link is never overwritten. Legacy programmatic save callers that
omit character fields retain voice-only behavior and can use administrator setup
in Voice Routing later.

Conversation handling reads approved local records only. Editing or regenerating
retains the prior approved revision until replacement approval. Announcements
remain personality-free. Voice filenames never establish character identity.

## Validation and rollout

The offline adapter/callback tests live in `character_integration_tests` and use
mock audio, HTTP transports and a Gradio component stub. The cross-repository
acceptance test uses one Atlas profile and the real OpenJarvis routes and storage,
with research/model calls mocked. They do not download model weights or contact
production.

Before production rollout, verify the deployed Gradio version and the actual
UI, existing OpenJarvis API authentication, SearXNG, Qwen and Home Assistant
connections. Check one newly created profile through review, approval, voice
selection and a neutral announcement. Installing or publishing this source does
not deploy either service or restart it. Keep deployment and rollback decisions
separate from profile approval.
