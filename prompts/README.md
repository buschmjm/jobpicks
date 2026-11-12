# Versioned prompt files

Prompt templates live here as Markdown files with YAML front-matter.

## Front-matter schema (E2.5)

```yaml
---
model: qwen2.5:7b-instruct
version: 1
schema: resume_parse_v1
---
```

## Planned prompts

- `resume_parse.md` — resume → structured profile JSON
- `job_normalize.md` — unstructured job posting → normalized fields
- `match_explain.md` — top-match explanation bullets

Do not hardcode prompts in Python; load from this directory.
