---
name: setup
description: Checks and installs what the clipping machine needs (ffmpeg, uv, a font, disk space) on Mac or Windows and confirms the Chrome extension is connected. Use for "setup", "install", "it doesn't work", or the first run of /gta.
---

# Setup

1. Run `uv run scripts/doctor.py`. If `uv` itself is missing, tell the user to install it
   (Mac/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`, Windows:
   `winget install --id astral-sh.uv -e`) and reopen the terminal.
2. For each ✗, show the fix line it printed and offer to run it. Installing software changes the
   user's machine, so run an install command only after they say yes. On Windows, a new
   terminal is needed before a fresh `ffmpeg` install shows up.
3. Check Claude in Chrome: load its tools and call `tabs_context_mcp`. If it isn't connected,
   point the user to the Claude in Chrome extension and to connecting it in Claude Code.
4. Run doctor again until it ends with "All good".

The first transcription downloads a speech model (0.5 to 1.6 GB). That's expected, once.
