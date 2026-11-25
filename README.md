agentic-unemployment
====================

A CLI tool for crawling job listings, scoring them against your resume, and
sending Telegram notifications.

Commands
--------

- ``au run``           Crawl, score, and notify in one pass (cron/worker use)
- ``au crawl``         Crawl Jobinja and/or JobVision and store jobs
- ``au score``         Score pending jobs against the resume
- ``au notify``        Send Telegram notifications for scored matches
- ``au stats``         Show database, resume and notification counts
- ``au resume check``  Inspect the combined resume and its hash
- ``au github enrich`` Generate ``resume/github.md`` from a GitHub profile
- ``au github test``   Check GitHub API connectivity
- ``au telegram test`` Send a test Telegram message

Installation
------------

1. Clone the repository.

2. Create a virtual environment and install dependencies:

   ``python -m venv .venv && source .venv/bin/activate``
   ``pip install -e .``

3. Copy ``.env.example`` to ``.env`` and fill in your credentials
   (Telegram token/chat ID, GitHub token, LLM key, etc.).

Usage
-----

``au crawl``::

    au crawl --keyword python --remote

``au crawl`` with JobVision only::

    au crawl --source jobvision --keyword python --remote

``au score``::

    au score --limit 20

``au notify``::

    au notify --min-score 60

``au run`` (crawl + score + notify)::

    au run --max-pages 2 --delay 2.0

Configuration
-------------

See ``.env.example`` for all options. Key variables:

- ``DB_PATH``           Path to the SQLite database (default: ``data/jobs.db``)
- ``TELEGRAM_TOKEN``    Telegram bot token
- ``TELEGRAM_CHAT_ID``  Your chat ID
- ``TELEGRAM_MIN_SCORE`` Minimum score to trigger a notification (default: 50)
- ``OUTBOUND_PROXY``    SOCKS5 proxy URL for blocked services
- ``GITHUB_USERNAME`` / ``GITHUB_TOKEN``  For GitHub enrichment
- ``LLM_API_KEY``       LLM API key

Source selection
----------------

``au crawl`` accepts ``--source`` (repeatable) to limit which job source(s)
to query. Accepted values are ``jobinja`` and ``jobvision``. If omitted, all
configured searches run.

Default searches are defined in the ``SearchSpec`` list and cover python and
backend queries at both remote and on-site settings for each source.