# Naukri Job Automation

Python automation for collecting recommended jobs, scoring them with an AI
provider, answering application questions, and recording application
outcomes.

## Safety and configuration

This project automates actions on a third-party job site. Review selectors,
rate limits, and the site's terms before use. Never commit credentials,
resume files, browser profiles, or generated `data/*.json` files.

Create a local environment and install dependencies:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Configure providers and paths through the local settings file used by
`naukri_bot.settings.Settings`; API keys default to empty values and are never
required in source control.

## Development

```sh
make build
make lint
make test
```

The test suite covers filesystem-backed settings and application logging
without launching a browser or contacting external services. Browser flows
require a local Playwright installation and an authenticated profile.

## Structure

- `naukri_bot/naukri_bot.py` coordinates browser automation.
- `naukri_bot/ai_engine.py` contains provider integrations.
- `naukri_bot/resume_parser.py` extracts PDF, DOCX, and text resumes.
- `naukri_bot/apply_logger.py` records outcomes and daily limits.
- `naukri_bot/settings.py` manages local configuration defaults.
- `docs/ARCHITECTURE.md` and `docs/MODERNIZATION.md` describe boundaries and
  the audit baseline.
