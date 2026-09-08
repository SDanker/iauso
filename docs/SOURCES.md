# Sources and technical scope

Reviewed: 7 September 2026. Python adaptation built for the Raspberry Pi
Zero 2 W + Waveshare 2.15inch e-Paper HAT+ (G).

## Codenotch

Repository: https://github.com/vinzdg/codenotch

Reviewed commit: `743601acd69e701131602b88082fcaeee0c2e88b`.

- [ClaudeOAuthProvider.swift](https://github.com/vinzdg/codenotch/blob/743601acd69e701131602b88082fcaeee0c2e88b/Sources/Providers/ClaudeOAuthProvider.swift): OAuth usage endpoint, beta header, `limits`, `five_hour` and `seven_day` fields, and how both formats are merged.
- [CodexLocalProvider.swift](https://github.com/vinzdg/codenotch/blob/743601acd69e701131602b88082fcaeee0c2e88b/Sources/Providers/CodexLocalProvider.swift): `GET https://chatgpt.com/backend-api/wham/usage` with the Codex session and `ChatGPT-Account-Id`.
- [CodexUsage.swift](https://github.com/vinzdg/codenotch/blob/743601acd69e701131602b88082fcaeee0c2e88b/Sources/Providers/CodexUsage.swift): primary windows, percentages, duration and absolute or relative reset. The code-review counter is not mixed into the main quota.
- `ClaudeCredentials.swift` and `CodexCredentials.swift`: reading sessions without modifying or renewing credentials.

This adaptation does not run the Swift code and does not replicate the macOS
interface. It implements the queries and the meaning of their data in Python,
adding interval persistence, a receiver file, validation, e-ink rendering and
tests.

## Waveshare

- [Product: 2.15inch e-Paper HAT+ (G)](https://www.waveshare.com/2.15inch-e-paper-hat-plus-g.htm): 296 × 160; black, white, yellow and red; SPI interface; full refresh of roughly 20 seconds.
- [Manual](https://www.waveshare.com/wiki/2.15inch_e-Paper_HAT%2B_%28G%29_Manual).
- [Official e-Paper repository](https://github.com/waveshareteam/e-Paper).

Commit of the included files: `a794fbc39656b0f93938d1ffb3fdc77eaed9e9fc`.

`RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in15g.py` and
`epdconfig.py` are included unmodified. The adaptation subclasses `EPD` to add
a BUSY wait limit. It does not modify registers, initialization sequences or
waveforms. The vendor's `getbuffer()` rotates the horizontal 296 × 160 image to
the internal 160 × 296 orientation and produces 11,840 bytes, two bits per
pixel.

### Additional panels (v1.2, not tested on physical hardware)

Commit of the included files: `06e834491bf62023a1b86a481b4530978883d2c4` (same
repository; `epdconfig.py` is identical to the previous commit — verified byte
by byte with `diff`).

`epd2in13_V4.py`, `epd2in13b_V4.py`, `epd2in9_V2.py`, `epd2in9b_V4.py`,
`epd4in2_V2.py`, `epd7in5_V2.py` and `epd7in5b_V2.py` are included unmodified.
`iauso/panels.py` maps each one to its size and color mode; `iauso/display.py`
splits the rendered image into two layers (black and color) for the "b" models,
using the same official `getbuffer()`/`display(imageblack, imagered)` pattern.
See [PANELS.md](PANELS.md) for the scope and limitations of this part.

## Authentication

- [OpenAI: Codex authentication](https://developers.openai.com/codex/auth): subscription sessions, local storage and device-code authentication.
- [Anthropic: Claude Code authentication](https://code.claude.com/docs/en/authentication): credential storage per operating system.
- [Anthropic: Claude Code with Pro or Max](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan).

The quota endpoints belong to the providers, and their use here is not a
promise of a stable public API. Only read queries with the user's own sessions
are implemented. The user completes sign-in in the official tools.

## Docker server, version 1.1

- [Docker Compose: secrets](https://docs.docker.com/compose/how-tos/use-secrets/): mounting the private file at `/run/secrets/api_token`.
- [Gunicorn on PyPI](https://pypi.org/project/gunicorn/): WSGI server; this delivery pins 26.2.0.
- [OpenAI: Codex CLI](https://github.com/openai/codex): official `@openai/codex` package for the temporary authentication container.
- [Anthropic: setup](https://code.claude.com/docs/en/setup): `@anthropic-ai/claude-code` package and CLI requirements.
- [Anthropic: CLI reference](https://code.claude.com/docs/en/cli-reference): `claude auth login`, without `--console`, for the subscription session.

The API itself is new in this adaptation; it is not part of the original Swift
repository. The collector stays separate from the HTTP process, so several
displays share the same reading. The HTTP container only mounts the public
snapshot folder and the API key; provider sessions are mounted only in the
collector and in the temporary authentication container.
