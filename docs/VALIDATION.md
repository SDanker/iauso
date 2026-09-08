# Delivery validation

Date: 7 September 2026.

Version 1.2. Result: **30 tests passing** with
`python3 -m unittest discover -s tests -v`.

Relevant coverage:

- Configurable color thresholds: `warn_percent`/`crit_percent` do change the bar color, a single-ink panel never paints the second color and a monochrome one paints none; out-of-range values, or `warn_percent` greater than `crit_percent`, are rejected.
- Claude: new and old formats, merging without duplicates, and missing values.
- Codex: main quota, real duration and absolute/relative resets.
- Rejection of invalid percentages, expired sessions and API keys instead of sessions.
- HTTP 401, persistent 429 backoff, cache with its original date, and account/token change.
- Disabled providers: their credentials are never read.
- Snapshot without secrets, date validation, stale data and rejection of DEMO as a real source.
- 296 × 160 image limited to black, white, yellow and red; preview inspected.
- Official `getbuffer()`: 11,840 bytes; correct encoding of the four colors.
- Minimum interval between refreshes, daily maintenance and backoff after a simulated hardware failure.
- Command-line flow for DEMO and receiver modes, without GPIO or accounts.
- SSH push with a fixed command, data over stdin, and rejection of options injected into the target.
- API over real local HTTP: Bearer authentication, routes/methods, 401/503 errors and no-cache headers.
- API without extra provider queries and output limited to public fields; private data injected in the tests is stripped from the response.
- HTTP client and Raspberry Pi CLI: reading the API and rendering 296 × 160 without reading local sessions.
- Server outage: keeps quota with its date, marks disconnection and discards readings from another server or out of order.
- Stale detection even while the API keeps working; redirects blocked and HTTPS as the default.
- Server initializer: private folders/key, and preservation of keys/configuration on a second run.

Additional checks: installer syntax with `bash -n`, Python compilation, and
generated units accepted by `systemd-analyze verify` (exit 0). The two included
Waveshare files were compared byte by byte against the documented commit.

**Gunicorn 26.2.0** was also run for real, with two processes and two threads
each, using the same HTTP arguments as the Dockerfile: correct startup and 200,
401 and 503 responses verified with simulated data. The test key does not appear
in stdout/stderr. The Compose YAML was analyzed and separate mounts, UID/GID
1000, the default local port and the temporary authentication profile were
verified.

## Added in version 1.2

Verified with real Docker Compose: image builds, `collector` and `api` startup,
real Claude and Codex logins, and 200 responses from `/healthz` and `/v1/usage`
with real quota from both providers. The `OPTIONS` preflight and the CORS
headers were also checked with `curl` against the running server.

The eight panels in the registry (`iauso/panels.py`) were rendered and each one
was checked to use only the colors its ink allows: black and white on the
monochrome ones, and black/white/color on the "duo" ones. **The seven panels
other than the 2.15G were not tested on physical hardware**: their driver code
is the official Waveshare one, unmodified, but real SPI communication with those
panels remains unverified. See [PANELS.md](PANELS.md).

The systemd units in [WITHOUT_DOCKER.md](WITHOUT_DOCKER.md) and the examples in
[INTEGRATIONS.md](INTEGRATIONS.md) were not tested on a real server either; each
recipe in [CONFIGURATION.md](CONFIGURATION.md) was verified to load and render,
and every internal documentation link was verified to resolve.

Pending on the user's machines: the official CLI downloads/logins on other
setups, connectivity between server and Raspberry Pi in other topologies, power
and HAT mounting, GPIO/SPI permissions, physical refresh, and the current
behavior of the authenticated services.
