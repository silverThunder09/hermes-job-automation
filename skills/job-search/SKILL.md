---
name: job-search
description: Use for the daily job-posting workflow, fit scoring, application-document drafts, review queue, or application-state checks in this project.
---

# Job search and application preparation

## Single-posting tailoring and image descriptions

A supplied job URL with an attached resume or portfolio follows [the single-job skill](../job-tailoring/SKILL.md), not this batch pipeline. For local posting images or PDFs only, follow its [original-preservation and OCR review steps](../job-tailoring/SKILL.md#local-ocr). Do not fill missing applicant facts from the example profile.

## Selected collection runtime

For cloud collection, check [ADR-0011 for the approved scope](../../docs/adr/0011-private-collection-writer.md), the [selected path and legacy code](../../docs/PLATFORM_ACCESS.md#선택한-수집-경로와-기존-코드), and [current integration status](../../README.md#현재-프로젝트-상태) before choosing a command. Do not invent a cloud collector command or use legacy collector status as a cloud test result. For scheduling, follow the [operations guide](../../docs/OPERATIONS.md#예약과-재부팅).

Run the existing Python review workflow in this order:

1. Read the current profile from `profile.json`. Before accessing a site, apply the [platform proceed/stop criteria](../../docs/PLATFORM_ACCESS.md#진행중단-기준); stop on login, CAPTCHA, or OTP instead of bypassing them. Confirm DB and external-write scope against [execution effects](../../docs/OPERATIONS.md#실행-단계) before running the CLI.
2. Use `python -m hermes_job_automation.cli run --collect-only` only for the existing Python pipeline and user-reviewed manual imports, not as the new cloud collector. Old Saramin API settings can still make live calls; do not activate or fall back to that path. Agent-researched cloud output needs the [approved dedicated save path](../../docs/SUPABASE_STATE.md#클라우드-수집-결과의-save-only-소비자) and exact read-back; manual import accepts only genuinely user-reviewed records. Record disabled or failed sources separately from a successful zero-result search.
3. Open data/to-review.json. Recheck every posting's deadline, city, experience, education, and employment type against the detail data included by its source. Exclude explicit degree requirements above high school and mandatory paid backend experience of one year or more. Treat missing or contradictory requirements as review.
4. Score only eligible or review postings. Use technical fit 35, work fit 30, project fit 25, and preferred qualifications 10. Every rationale must point to a supplied posting fact and a verified profile fact. QA employment is not paid backend experience.
5. Draft company-specific resume and cover-letter text only for eligible postings with total score at least MINIMUM_SCORE. Use the profile's verified facts; preserve its limitations. Never add unverified jobs, qualifications, skills, quantities, or outcomes.
6. Save a JSON file with the format below. If more than ten postings remain, include the ten highest-ranked eligible or review postings and list the remaining posting keys in the summary.
7. Run `python -m hermes_job_automation.cli finalize --file <review-json>` only within the confirmed DB-write scope. It rechecks eligibility and draft figures and creates local DOCX and Korean PDF files.
8. Add `--execute` only when the external targets are configured and approved as described in [execution effects](../../docs/OPERATIONS.md#실행-단계).
9. Report collection counts, disabled sources, exclusions, scores, documents, external-write status, and any missing configuration. Never represent a draft as submitted.

Review JSON schema:

    {
      "evaluations": [
        {
          "posting_key": "platform:id",
          "evaluation": {
            "technical_fit": 0,
            "work_fit": 0,
            "project_fit": 0,
            "preferred_qualifications": 0,
            "total": 0,
            "eligibility": "eligible",
            "rationale": ["posting requirement matched to a verified applicant fact"],
            "gaps": ["missing posting detail or requirement"]
          },
          "documents": {
            "resume": "reviewed Korean resume draft",
            "cover_letter": "reviewed Korean cover-letter draft"
          }
        }
      ]
    }

## Application state

Default to draft and review. Before any real submission, follow the [per-posting approval and duplicate-prevention rules](../../docs/OPERATIONS.md#제출-승인). Stop for human review on a challenge or unknown result; do not retry an uncertain submission.
