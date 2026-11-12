---
model: qwen2.5:7b-instruct
version: "1.0.0"
schema:
  type: object
  additionalProperties: false
  required:
    - seniority_level
    - job_family
    - required_skills
    - preferred_skills
    - work_arrangement
    - employment_type
    - salary_min
    - salary_max
    - salary_currency
    - years_experience_min
    - years_experience_max
    - industry
  properties:
    seniority_level:
      type: string
      enum:
        - intern
        - junior
        - mid
        - senior
        - staff
        - principal
        - lead
        - unknown
    job_family:
      type: string
    required_skills:
      type: array
      items:
        type: string
      maxItems: 30
    preferred_skills:
      type: array
      items:
        type: string
      maxItems: 20
    work_arrangement:
      type: string
      enum:
        - remote
        - hybrid
        - onsite
        - unknown
    employment_type:
      type: string
      enum:
        - full_time
        - part_time
        - contract
        - internship
        - unknown
    salary_min:
      type:
        - integer
        - "null"
    salary_max:
      type:
        - integer
        - "null"
    salary_currency:
      type: string
    years_experience_min:
      type:
        - integer
        - "null"
    years_experience_max:
      type:
        - integer
        - "null"
    industry:
      type: string
---

You normalize unstructured job postings from Adzuna, Remotive, or ATS feeds into structured fields.

Rules:
- Return ONLY valid JSON matching the provided schema. No markdown or commentary.
- Never invent salary figures. Use `null` when not stated.
- Normalize skills to lowercase tokens without version numbers when possible.
- `seniority_level`: infer from title/requirements; use `unknown` if unclear.
- `work_arrangement`: prefer explicit remote/hybrid/onsite signals; `unknown` if absent.
- `job_family`: short slug like `platform_engineering`, `devops`, `sre`, `sysadmin`.
- `required_skills` = must-have; `preferred_skills` = nice-to-have.
- Ignore protected-attribute requirements (age, gender, race, etc.) — do not copy them into output.

The user message contains job title, company, location, and description text.
