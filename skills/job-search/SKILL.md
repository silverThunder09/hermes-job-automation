---
name: job-search
description: Use for the daily job-posting workflow, fit scoring, application-document drafts, review queue, or application-state checks in this project.
---

# Job search and application preparation

## Single-posting tailoring and image descriptions

When the user supplies a job URL with an attached resume or portfolio, first read `skills/job-tailoring/SKILL.md`. Follow posting analysis (DOM plus images/OCR) -> official company-site analysis (skip with a reason when unavailable) -> tailoring a separate copy -> post-edit fit/factuality review -> local result storage. The existing batch pipeline below remains separate; a skill procedure is not a claim that autonomous browser collection or source-resume editing is already wired into Python.

For local posting images, use `python -m hermes_job_automation.cli ocr-image --file <image> --language ko --output <new-json>`. Compare critical fields with the original; OCR output is never automatically verified. Text-based PDFs should be extracted without OCR, but still inspect diagrams and image-only regions. Do not infer missing applicant facts from profile.example.json when an attached document does not establish them.

## Selected collection runtime

Read [ADR-0011](../../docs/adr/0011-private-collection-writer.md) for collection/runtime work. PC-on starts cloud browser/MCP work from the local agent; PC-off uses a GitHub Actions scheduled cloud run. Both use the existing Supabase. The Saramin official-API operating path is retired: do not request its approval/key or use legacy collector statuses as evidence that the selected cloud path failed. The browser-to-remote-storage integration is not yet implemented, and schedules require separate activation approval after the bounded manual verification. Preserve platform access, provenance, no-bypass and DB-write boundaries. Do not invent a cloud collection command or relabel agent research as user-reviewed input.

Run the existing Python review workflow in this order:

1. Read the current profile from profile.json and the platform access rules in docs/PLATFORM_ACCESS.md.
2. Use `python -m hermes_job_automation.cli run --collect-only` only for the existing Python pipeline and user-reviewed manual imports, not as the new cloud collector. It can still invoke the legacy Saramin API when its old settings are active; the retirement decision has not disabled that code. Do not activate it as a fallback. Agent-researched cloud output needs the approved dedicated save path and exact read-back; manual import accepts only genuinely user-reviewed records. Record disabled or failed sources separately from a successful zero-result search.
3. Open data/to-review.json. Recheck every posting's deadline, city, experience, education, and employment type against the detail data included by its source. Exclude explicit degree requirements above high school and mandatory paid backend experience of one year or more. Treat missing or contradictory requirements as review.
4. Score only eligible or review postings. Use technical fit 35, work fit 30, project fit 25, and preferred qualifications 10. Every rationale must point to a supplied posting fact and a verified profile fact. QA employment is not paid backend experience.
5. Draft company-specific resume and cover-letter text only for eligible postings with total score at least MINIMUM_SCORE. Use the profile's verified facts; preserve its limitations. Never add unverified jobs, qualifications, skills, quantities, or outcomes.
6. Save a JSON file with the format below. If more than ten postings remain, include the ten highest-ranked eligible or review postings and list the remaining posting keys in the summary.
7. Run python -m hermes_job_automation.cli finalize --file <review-json> to recheck eligibility and draft figures, then create local DOCX and Korean PDF files.
8. Only when Google credentials, the target sheet, Drive folder access, and Telegram settings are configured, the operator may run the same command with --execute to update the sheet, upload drafts, and send a summary.
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

The application workflow remains at draft and review. A CAPTCHA, OTP, login challenge, conflicting deadline, missing required field, or unknown submission result requires human review. Submit only when the application flow's exact platform, posting, and conditions already have an unexpired user approval record, AUTO_SUBMIT and FORM_AUTOFILL_ENABLED are true, and the posting has not been attempted before. Save the attempt before the final click. Accept success only when the page shows a receipt number or an explicit completion state.
