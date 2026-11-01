# KRISI Biology Studio ? Student Activation Recovery

## Purpose

This procedure handles interrupted or uncertain
student password activation attempts.

## Activation states

- pending: Activation has not started.
- processing: An activation attempt is reserved.
- activated: Password update was confirmed and
  activation was recorded in PostgreSQL.

## Safety rules

1. Never store student passwords in recovery logs.
2. Never expose Supabase service-role credentials.
3. Never automatically reset processing to pending.
4. Never infer password-update success from a timeout.
5. Never change activation state without investigation.
6. Record administrative recovery actions separately.

## Investigation

1. Identify the affected student profile.
2. Inspect activation_status and activation_started_at.
3. Review application logs without exposing secrets.
4. Check Supabase Auth user status.
5. Determine whether the password update was confirmed.
6. If the outcome remains uncertain, leave processing unchanged.

## Recovery decisions

Confirmed successful password update:
- Verify the correct Supabase user.
- Reconcile PostgreSQL activation state using a
  separately reviewed administrative procedure.

Confirmed unsuccessful password update:
- Reconcile the failed attempt only after confirming
  no earlier update remains in progress.

Unknown outcome:
- Keep processing.
- Escalate for manual investigation.

## Restrictions

Do not perform direct database recovery updates
without explicit authorization and verified evidence.

## Current implementation

The recovery inspection query is available.
Automated administrative recovery is not implemented.
