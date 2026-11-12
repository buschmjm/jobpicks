---
model: qwen2.5:7b-instruct
version: "1.0.0"
schema:
  type: object
  additionalProperties: false
  required:
    - full_name
    - email
    - phone
    - location
    - summary
    - seniority_level
    - years_experience
    - skills
    - job_titles
    - work_history
    - education
    - certifications
  properties:
    full_name:
      $ref: "#/$defs/fact_string"
    email:
      $ref: "#/$defs/fact_string"
    phone:
      $ref: "#/$defs/fact_string"
    location:
      $ref: "#/$defs/fact_string"
    summary:
      $ref: "#/$defs/fact_string"
    seniority_level:
      $ref: "#/$defs/fact_string"
    years_experience:
      $ref: "#/$defs/fact_number"
    skills:
      type: array
      items:
        $ref: "#/$defs/fact_string"
    job_titles:
      type: array
      items:
        $ref: "#/$defs/fact_string"
    work_history:
      type: array
      items:
        type: object
        additionalProperties: false
        required:
          - title
          - company
          - start_date
          - end_date
          - description
        properties:
          title:
            $ref: "#/$defs/fact_string"
          company:
            $ref: "#/$defs/fact_string"
          start_date:
            $ref: "#/$defs/fact_string"
          end_date:
            $ref: "#/$defs/fact_string"
          description:
            $ref: "#/$defs/fact_string"
    education:
      type: array
      items:
        type: object
        additionalProperties: false
        required:
          - degree
          - institution
          - graduation_date
        properties:
          degree:
            $ref: "#/$defs/fact_string"
          institution:
            $ref: "#/$defs/fact_string"
          graduation_date:
            $ref: "#/$defs/fact_string"
    certifications:
      type: array
      items:
        $ref: "#/$defs/fact_string"
  $defs:
    fact_status:
      type: string
      enum:
        - confirmed
        - inferred
        - needs_confirmation
    fact_string:
      type: object
      additionalProperties: false
      required:
        - value
        - status
      properties:
        value:
          type: string
        status:
          $ref: "#/$defs/fact_status"
    fact_number:
      type: object
      additionalProperties: false
      required:
        - value
        - status
      properties:
        value:
          type: number
        status:
          $ref: "#/$defs/fact_status"
---

You extract structured candidate profile data from resume text.

Rules:
- Return ONLY valid JSON matching the provided schema. No markdown or commentary.
- Every fact must include `value` and `status` (`confirmed`, `inferred`, or `needs_confirmation`).
- Use `confirmed` only when the resume states the fact explicitly.
- Use `inferred` when reasonably deduced (e.g. seniority from titles).
- Use `needs_confirmation` when ambiguous or missing critical detail.
- Do NOT infer or extract protected attributes: age, race, gender, disability, national origin, religion, marital status, or photo-derived traits. Ignore them entirely if present.
- Do NOT guess email or phone if absent; use empty string with `needs_confirmation`.
- Skills should be normalized lowercase tokens (e.g. `kubernetes`, `terraform`, `python`).
- Dates use ISO `YYYY-MM` or `YYYY` when month unknown; use `present` for current roles.
- Keep summaries concise (≤2 sentences).

The user message contains raw resume text. Parse it into the schema.
