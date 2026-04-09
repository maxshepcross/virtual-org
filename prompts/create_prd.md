You are creating a short Product Requirements Document, which is a plain-English brief for a feature or task.

## Goal

Turn a rough request into a clear brief that a junior engineer can understand.

## Rules

- Focus on the problem, the user, the core behavior, and what is out of scope.
- If the target repo is missing for code work, call that out clearly.
- Use plain English. Avoid jargon.
- Do not start implementation.
- Do not ask the user interactive questions in this step.
- If details are missing, capture them under `Open Questions` and keep going.

## Task Input

Title: {title}
Category: {category}
Description: {description}
Target repo: {target_repo}

## Output Format

Return markdown with these sections:

1. Overview
2. Goals
3. User Stories
4. Functional Requirements
5. Non-Goals
6. Technical Notes
7. Success Metrics
8. Open Questions

Return only the markdown brief.
