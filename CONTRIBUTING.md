# Contributing

Thanks for wanting to improve the Lynk & Co integration. Here is how to make that count.

## Ideas and bugs: open an issue

An issue is the preferred way to contribute, also for things you could build yourself with the help of LLMs (see below on the usage of LLMs). Use the matching template; each one asks for exactly what is needed to act on it:

- [Bug report](https://github.com/b12e/ha_lynkco_2025/issues/new?template=bug_report.yml) - attach the diagnostics download (device page, three dots, Download diagnostics). It is redacted and shows what your car reports.
- [Feature request](https://github.com/b12e/ha_lynkco_2025/issues/new?template=feature_request.yml) - describe what you want to achieve in Home Assistant, not only the sensor or action you miss. The API often offers more than one way to get there.
- [Model report](https://github.com/b12e/ha_lynkco_2025/issues/new?template=model_report.yml) - your car gets a Repairs notice about an unknown model, or an action is disabled for it although the official app has it.

## Pull requests

Pull requests are welcome too. To keep them easy to review and release:

- One change per pull request, against `main`.
- Give it a conventional title (`feat: ...`, `fix: ...`). The squash commit takes it, and it becomes the line in the release notes. `chore:`, `docs:` and `test:` changes do not show up there.
- If the change breaks existing setups (renamed entities, changed states or modes, removed actions), add a line starting with `Breaking:` to the description. It ends up in the caution block at the top of the release notes.
- Run the tests before pushing: `pip install -r requirements_test.txt`, then `python -m pytest` (Python 3.14; the harness is pytest-homeassistant-custom-component). CI runs them as well, plus hassfest and the HACS validation.
- Keep VINs, tokens, coordinates and addresses out of log messages, test fixtures and the pull request itself. `redact_vin` exists for a reason.

## Using an LLM

That is fine. So do I - this integration is developed with one as well and there's nothing wrong with that. I'd argue this integration wouldn't exist without the help of my dear friend Claude.

HOWEVER: if your plan is to tell your LLM model of choice "build X and make a pull request", skip that step and open an issue describing X instead. 

There's little point of us both burning tokens, and it costs me less time to do it myself than reviewing and re-testing a generated pull request (and making sure nothing malicious slips in), so you get the feature sooner.
