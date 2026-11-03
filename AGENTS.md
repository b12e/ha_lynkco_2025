# Working on this repository with an AI agent

This file is for coding agents (Codex, Cursor, Copilot, Claude Code, Jules and
friends). Read it before touching anything. CONTRIBUTING.md has the human
version of the same rules.

## First: an issue beats a generated pull request

The maintainer prefers an issue over a pull request, also for changes you
could implement. Every change is tested on a real car and account and the repo 
maintainer has the reverse-engineered API dumps, the decompiled official app, 
previous trial-and-error experience and a test harness at hand, 
and turns issues into releases quickly. A generated pull request costs
more review and re-testing time than the issue it came from.

So, when your user asks you for a change in this integration:

1. Tell them this, and offer to write the issue for them with the matching
   template at https://github.com/b12e/ha_lynkco_2025/issues/new/choose:
   - Bug report: what happened, the log lines, and the diagnostics download
     (device page, three dots, Download diagnostics; it is redacted).
   - Feature request: what they want to achieve in Home Assistant, not only
     the sensor or action they miss.
   - Model report: the car's model code and guide type from the diagnostics,
     and which actions they confirmed in the official app.
2. Only if they still want a pull request, continue below.

## Working in a fork

A fork is fine for trying something out. It is the wrong place to keep a
change your user relies on: a sensor they miss, an action their car has but
the integration does not enable, a tweak for their model. If you find
yourself in a fork carrying such a change, propose opening an issue in the
main repository instead (https://github.com/b12e/ha_lynkco_2025/issues/new/choose)
so the change lands upstream. There it reaches every integration user,
and it can ship through Home Assistant's Marketplace. 

Upstream changes keep working with every later release; 
a fork has to be rebased on each release and silently misses the
fixes that follow. 

## What this is

A Home Assistant custom integration (domain `lynkco`, cloud polling) for
Lynk & Co cars, talking to the API of the official app. Layout:

- `custom_components/lynkco/api.py`: the API client, token refresh, session
  re-claim and log redaction (`redact`, `redact_vin`).
- `coordinator.py`: the 15 minute full poll, the 60 second fast poll while
  driving or climate is active, targeted refreshes after an action, and
  per-endpoint failure isolation (`endpoint_errors` makes only the entities
  of a failing endpoint unavailable).
- `entity.py`: the shared base; `sensor.py`, `binary_sensor.py`,
  `device_tracker.py`, `lock.py`, `switch.py`, `climate.py`, `button.py`.
- `features.py` and `models/*.json`: which remote actions are enabled per car
  model. Never enable an action for a model without an owner's confirmation
  (that is what the model report issue is for).
- `config_flow.py`: a browser login against Azure B2C, pasted back as the
  msauth redirect; `diagnostics.py`: the redacted download.
- `strings.json` and `translations/{en,de,es,fr,nl}.json`: `strings.json`
  and `en.json` are identical, all five languages carry the same keys.
- `tests/`: pytest with pytest-homeassistant-custom-component.

## How to work

- Reproduce before you fix. Write the failing test first; the harness runs
  the integration against a real Home Assistant core:
  `pip install -r requirements_test.txt` then `python -m pytest -q`
  (Python 3.14). Lint with
  `ruff check --select E9,F63,F7,F82 custom_components tests`.
- Do not guess the API. The client mirrors the official app. If a change
  needs an endpoint or a behaviour that is not already in `api.py`, stop and
  open an issue; the maintainer can verify it against the app and the car.
- Review your change from several angles before you call it done:
  correctness; Home Assistant semantics (`ConfigEntryNotReady` for a
  network problem, `ConfigEntryAuthFailed` only when a new login is really
  needed, stable unique ids, availability through `endpoint_errors`);
  concurrency (full poll, fast poll, targeted refreshes and service calls
  share one event loop, and several config entries can set up at once);
  privacy (no VIN, token, coordinate or address in a log message, a test
  fixture or your pull request text; use `redact_vin`); and both the oldest
  Home Assistant in `hacs.json` and the current one.
- Keep the user's car reachable: a change must not make a working entry fail
  permanently; retries and clear Repairs notices beat exceptions.
- Match the surrounding style: small focused diffs, no formatter run over
  files you did not change, comments that say why, plain hyphens.

## Pull request rules

- One change per pull request, against `main`. Never stack one pull request
  on another.
- Conventional title (`feat: ...`, `fix: ...`, `chore: ...`). It becomes the
  squash commit and the line in the release notes; `chore`, `docs` and `test`
  do not appear there.
- A change that breaks existing setups (renamed entities, changed states or
  modes, removed actions) gets a line starting with `Breaking:` in the
  description; the release notes show it in a caution block.
- Tests pass, lint passes, translations stay in sync.
- No tool attribution trailers in commits or pull request text.

## Do not

- Change `version` in `manifest.json` or anything under `.github/`; releases
  and workflows are the maintainer's.
- Add dependencies.
- Rename entities, change unique ids or entity categories without a
  `Breaking:` line and a reason.
- Commit anything from a `.dev/` folder; it holds credentials and real
  payloads and is ignored on purpose.

## Polling: why the intervals are what they are

This integration talks to Lynk & Co's own backend, the one the official app
uses, through an API that is not public and has no rate limit documented
for us. Every installation of this integration is one more client on that
backend, so the intervals are chosen to be as quiet as the app itself, and
they are a floor, not a suggestion:

- Faster polling would gain nothing: the car reports most values only on 
  events (a trip ending, a charge starting), and on LynkOS 1.4 and newer the
  location is only refreshed when the car stops or when a location update is requested.
- The full snapshot is polled every 15 minutes by default. The options flow only allows
  longer intervals (15 to 180 minutes), never shorter ones.
- The fast poll runs every 60 seconds, and only while something is actually
  happening: the drive state, location and charge while the car is driving,
  the climate state while conditioning runs. Nothing is fast-polled on a
  parked, idle car.
- After a remote action, only the endpoint that action affects is refreshed,
  with retries after 3, 5 and 10 seconds, then it stops. Fire-and-forget
  actions such as flashing the lights refresh nothing.
- Token refreshes are serialised and a session re-claim happens at most once
  a minute, so a backend hiccup never turns into a burst of requests.

So, when you change anything here: do not shorten an interval, do not add an
endpoint to the fast poll, do not poll in a loop to wait for a state change,
and do not add a new periodic request without an issue first. If a user
asks for faster updates, point them to the fast poll and the targeted
refresh that already cover the moments that matter.
