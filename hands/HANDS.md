# HANDS.md — the agent-browser execution protocol

social-agent is the **brain**: watchers observe, propose, and gate.
The agent's browser is the **hands**: it performs approved actions in a
real browser session (e.g. Muse's server-side Chromium, watched live in
the browser card).

## The loop

1. social-agent proposes an action → it lands in the approval queue.
2. The operator approves it (`engage approve <id>`, `post approve`, …).
3. The operator (or the agent) issues an execution ticket:
   `social-agent hands ticket create --platform tiktok --account main --action like --target <url> --approval-id <qid>`
   Ticket creation runs the full guard order —
   **ToS > crisis > approvals > rate limits > quiet hours** — and fails
   closed if any layer denies.
4. The agent reads the ticket (`hands ticket show <id>`), performs the
   `instructions` in its own browser session, and reports back.
5. The operator closes the loop: `hands ticket fulfill <id> --result …`
   A ticket can only be fulfilled once — duplicates are refused.

## Ticket schema

```json
{
  "ticket_id": "t-…",
  "idempotency_key": "t-…",
  "created_at": "…", "created_at_ts": 0,
  "platform": "tiktok",
  "account_label": "main",
  "action": "like",
  "params": { "target_url": "…" },
  "receipts": {
    "tos": { "status": "allowed", "acknowledged_risk": false },
    "approval_id": "q-…",
    "rate_limit": { "remaining_hour": 99, "remaining_day": 999 },
    "quiet_hours": false
  },
  "instructions": "plain-language steps for the agent browser",
  "status": "open | fulfilled | cancelled"
}
```

## Credentials

Logins live in the agent's secure credential store (or the operator's
own browser) — **never** in the repo, never in social-agent state.
`social-agent doctor` asserts this. Tickets carry handles only.

## Actions

like, comment, follow, unfollow, follow_user, unfollow_user, post_text,
post_video, post_photo, upload_video, dm_send, hide_comment, subscribe.

Every action maps onto a ToS action class in
`platforms/<platform>/tos_rules.yaml`. Prohibited stays prohibited;
`tos.acknowledged_risk` in `policy.yaml` is the only opt-in, and it is
logged loudly.
