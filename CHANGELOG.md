# Changelog

Evalrite is a maintained fork of [OpenAI Evals](https://github.com/openai/evals). Every fix below was written by its credited author as an open pull request upstream; their commits keep their authorship here.

## Unreleased

### Added

- Enterprise readiness eval: 47 questions on fictional security and data protection policies, graded deterministically for JSON validity, grounded citations, abstention and prompt-injection resistance (`evals/elsuite/enterprise_readiness`)
- `generation/direct/anthropic` solver, which runs any Claude model passed with `--completion_args model_name=...`

### Fixed

- Replace the removed Anthropic `ContentBlock` type with `TextBlock` (Anthropic commit of openai/evals#1537, by sakher; that PR's OpenAI and Gemini changes aren't brought in yet)
- Send Anthropic messages as plain dicts so the solver works with current Anthropic SDKs, where `MessageParam` is a Union, and join all text blocks in a reply; adds a stubbed-client test that needs no API key

### Fixed (brought in from upstream pull requests)

- Create the registry's OpenAI client only when needed, so importing works without an API key (openai/evals#1724, by Sylvester Kaczmarek)
- Read EVALS_SHOW_EVAL_PROGRESS as a true or false value (openai/evals#1751, by Sylvester Kaczmarek)
- Reset max_samples on every oaieval run (openai/evals#1728, by Sylvester Kaczmarek)
- Stop jsondumps changing its input when exclude_keys is used (openai/evals#1762, by Sylvester Kaczmarek)
- Stop the formatting scrub changing caller-owned chat prompts (openai/evals#1726, by Sylvester Kaczmarek)
- Don't treat empty prompt lists as chat prompts (openai/evals#1801, by Sylvester Kaczmarek)
- Count matching JSON nulls as correct in JsonMatch (openai/evals#1764, by Sylvester Kaczmarek)
- Handle zero denominators in precision, recall and F-score (openai/evals#1851, by reginaldalfret)
- Fix bootstrap accuracy std on single-sample runs and resampling (openai/evals#1834, by Arpan Mondal)
- Leave unreadable model-grader output out of scores (openai/evals#1718, by Sylvester Kaczmarek)
- Fix the TypeError when adding up nested token usage (openai/evals#1696, by NikhilMiddaGeek)
- Restore recorder context after exceptions (openai/evals#1741, by Sylvester Kaczmarek)
- Stop HttpRecorder silently dropping events (openai/evals#1820, by Samsul)
- Cap API retries and drop dead error checks (openai/evals#1821, by Alphaxiaoteng)
- Count async progress from the scheduled samples (openai/evals#1754, by Sylvester Kaczmarek)
- Keep failed eval-set commands out of resume checkpoints (openai/evals#1740, by Sylvester Kaczmarek)
- Stop registry alias cycles hanging resolution (openai/evals#1850, by Aarav)
- Make the Snowflake connector an optional dependency (openai/evals#1717, by Sylvester Kaczmarek)
- Use Ruff instead of the duplicate Autoflake hook (openai/evals#1749, by Sylvester Kaczmarek)

### Not brought in yet

- openai/evals#1776 (LAMBADA word boundaries): its new tests fail because `DummyRecorder` drops events when it has no run spec. Needs a test fix first.
