---
name: communication-preferences
description: Standing user-facing communication and note-format conventions for Joseph.
metadata:
  type: project
---

# Communication preferences

Every user-facing message must begin exactly with `Joseph,` on its own line, followed by a blank line and the message body. This applies to commentary updates and final responses in every future session.

For Claude chats, include this exact instruction in every project handoff or session-start prompt. It cannot override Claude's system-level behavior in unrelated chats.

Joseph runs the interactive localhost review himself. After automated validation, say plainly when the website is ready to inspect and provide the localhost command or URL if useful. Do not start or keep a Streamlit development server running unless Joseph explicitly asks.

For definition or concept-overview requests, default to a dense one-page note-taking format. Use: a one-sentence intuition; precise definition and what the method tests; compact formula with symbols defined; assumptions; ML use cases; pros and cons; one example grounded in Joseph's actual workspace; and a short decision rule or takeaway. Optimize for scanning, distinguish a proposed use from code that is already implemented, and keep the response to roughly one rendered page unless Joseph asks for more depth.
