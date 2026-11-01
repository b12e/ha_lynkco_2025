# Contributing

Thanks for wanting to improve the Lynk & Co integration. Here is how to make that count.

## Ideas and bugs: open an issue

An issue is the preferred way to contribute, also for things you could build yourself. Use the matching template; each one asks for exactly what is needed to act on it:

- [Bug report](https://github.com/b12e/ha_lynkco_2025/issues/new?template=bug_report.yml) - attach the diagnostics download (device page, three dots, Download diagnostics). It is redacted and shows what your car reports.
- [Feature request](https://github.com/b12e/ha_lynkco_2025/issues/new?template=feature_request.yml) - describe what you want to achieve in Home Assistant, not only the sensor or action you miss. The API often offers more than one way to get there.
- [Model report](https://github.com/b12e/ha_lynkco_2025/issues/new?template=model_report.yml) - your car gets a Repairs notice about an unknown model, or an action is disabled for it although the official app has it.

Changes are tested on a real car and account before they ship, including the shared-account setup. An issue gets that treatment for free.

## Pull requests

Pull requests are welcome too. To keep them easy to review and release:

- One change per pull request, against `main`.
- Give it a conventional title (`feat: ...`, `fix: ...`). The squash commit takes it, and it becomes the line in the release notes. `chore:`, `docs:` and `test:` changes do not show up there.
- If the change breaks existing setups (renamed entities, changed states or modes, removed actions), add a line starting with `Breaking:` to the description. It ends up in the caution block at the top of the release notes.
- Run the tests before pushing: `pip install -r requirements_test.txt`, then `python -m pytest` (Python 3.14; the harness is pytest-homeassistant-custom-component). CI runs them as well, plus hassfest and the HACS validation.
- Keep VINs, tokens, coordinates and addresses out of log messages, test fixtures and the pull request itself. `redact_vin` exists for a reason.

## Using an LLM

That is fine. This project is developed with one as well.

But if your plan is to tell your model "make a pull request for X", skip that step and open an issue describing X instead. I will do the vibecoding part myself, with the API knowledge, the decompiled app, the test harness and a real car at hand. That costs me less time than reviewing and re-testing a generated pull request, and you get the feature sooner.
