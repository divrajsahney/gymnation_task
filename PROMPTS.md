# AI conversations

Tool: Claude (claude.ai), model Claude Opus 5.5. One conversation.

> TODO before submitting: replace or extend this with the full exported conversation, including Claude's replies.

## Prompt 1

> https://forms.gymnation.com/f/hAh5gfoF8s7MZgJEE-c6f8KE?src=basim
> can you access this page

Claude fetched the page and summarised the role, the task and the form fields.

## Prompt 2

> (attached the full task brief as a text file)
> This is the task brief, give me steps to build this

Claude produced a step-by-step plan covering:
- the Docker contract
- strict validation
- phone classification patterns
- integer half-up rounding
- due-date clamping and the N/P anchor
- the reconciliation rules
- a concurrency test
- what goes in NOTES/PROMPTS

## Prompt 3

> Write the whole codebase and give me the zip

Claude wrote the app, tests, Dockerfile and NOTES.md, ran the suite (71 tests) and smoke-tested a live server. Bugs found along the way:
- One of its own test expectations had the wrong `invoice_no`. Mar 2027 is invoice 7 for a 20 Sep 2026 start; the test said 8.
- A tie-break test did not actually produce a tie. It was rewritten to use a 1-fils plan, where FIRST and MONTHLY land in the same month with the same total.
