# KRISI Biology Studio v3 implementation plan

Development branch: `feature/biology-studio-v3-foundation`. Never merge before tests, security review and migration backup.

## Foundation
- [x] Add a compatible SQLite migration for the Supabase user ID field.
- [x] Implement a teacher-facing visual quiz builder.
- [ ] Verify teacher provisioning and Supabase identity mapping end-to-end.
- [ ] Add application integration tests and CI.
- [ ] Standardize Europe/Dublin booking time handling.
- [ ] Define PostgreSQL as the durable production store and migrate legacy SQLite data carefully.
- [ ] Add audit logs, rate limits, access controls, and privacy/retention policies.

## Learning workflows
- [ ] Private lesson-material library (validated files, size limits, per-student access).
- [ ] Assignments, deadlines, submissions, teacher feedback and revision history.
- [ ] Student progress by lesson/topic, including quiz attempts and assignment completion.
- [ ] Availability calendar with timezone-aware conflict checks and cancellation rules.
- [ ] Email notifications via a transactional provider with retries and opt-outs where applicable.
- [ ] Downloadable progress reports and certificates with teacher approval.

## Interactive classroom
- [ ] Provider-hosted video classroom with short-lived, authorized meeting access.
- [ ] Shared whiteboard with teacher-controlled rooms and safe collaboration.
- [ ] Interactive biology diagrams and accessible labeling exercises.

## Release gates
- [ ] Unit, integration and browser tests pass.
- [ ] Student-to-student isolation and teacher role checks verified.
- [ ] Data migration tested on a sanitized backup.
- [ ] Consent, safeguarding and privacy reviewed for underage students.
- [ ] Staging deployment verified before any production release.

## Current limits
This branch is not production-ready. No emails are sent and no live classroom is hosted by these initial commits.
