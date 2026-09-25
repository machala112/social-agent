# Platform capabilities matrix

Honest summary of what social-agent can do per platform. "Hands" means an
execution ticket (`hands ticket create`) fulfilled in the agent's own
logged-in browser session (e.g. Muse's server-side Chromium, watched live
in the browser card). social-agent never drives a browser itself: it
proposes, gates, and logs; the agent's browser performs. There is no API
backend: no API clients, no API keys, no OAuth apps — this repo contains
zero platform-API integrations by the account owner's explicit order.

| Capability | TikTok | X | Instagram | Facebook | YouTube | Reddit | LinkedIn |
|---|---|---|---|---|---|---|---|
| Read feed / timeline | hands | hands | hands | hands | hands | hands | hands |
| Read profile + follower counts | hands | hands | hands | hands | hands | hands | hands |
| Read comments | hands | hands | hands | hands | hands | hands | hands |
| Read notifications | hands | hands | hands | hands | hands | hands | hands |
| Read DMs | hands | hands | hands | hands | n/a | hands | hands |
| Post content | hands | hands | hands | hands | hands | hands | hands (drafts only, human posts) |
| Like | hands | hands | hands | hands | hands | upvote: refused (vote manipulation) | react: refused (ToS) |
| Comment / reply | hands | hands | hands | hands | hands | hands | refused (ToS) |
| Follow / subscribe | hands | hands | hands | hands | hands | hands | follow/connect: refused (ToS) |
| Repost / retweet / share | hands (share) | hands | share to story via hands | hands (share) | n/a | crosspost via hands | refused (ToS) |
| DM send | hands (throttled) | hands | hands | hands | n/a | hands | refused (spam) |

## Auth notes

- **The agent browser** is the only execution path everywhere: the user
  signs in through the agent's secure credential flow; social-agent never
  sees the password and never stores credentials. Tickets carry handles
  only.
- There is no alternative auth path. Any `backend`, `api_key`, `api_secret`,
  or OAuth config for a social platform is not supported and never was
  shipped.

## Rate limits enforced by social-agent

See `policy/policy.yaml` (`rate_limits`). The CLI refuses acting operations
past the per-hour/per-day caps regardless of platform headroom. Every
execution ticket flows through the central rate-limit controller — the
agent browser is hands, not a bypass.

## Terms of Service compliance (per-platform)

Each platform ships `platforms/<name>/terms.md` (human-readable rules with
official source links and a last-checked date) and `platforms/<name>/tos_rules.yaml`
(machine-readable: `prohibited` / `restricted` / `allowed` per action class,
enforced by `platforms/tos.py`).

The ToS layer runs **first** — above missions, autonomy, approvals, quiet
hours, and rate limits. A `prohibited` entry refuses the action outright
(exit 2, logged to `refusals.jsonl`); a `restricted` entry proceeds but prints
the platform's constraint as an advisory. No mission or approval can override
a prohibition.

Key platform-specific outcomes (see each `terms.md` for sources):

- **X is the strict case.** X's developer guidelines require automation only
  through the official X API and prohibit non-API automation. This tool is
  browser-driven by the owner's explicit order, so automated likes, comments,
  follows, reposts, DMs, and browser-based data collection are **prohibited**
  on X. They proceed only under the explicit `tos.acknowledged_risk: [x]`
  opt-in, which downgrades the prohibition to restricted with a loud logged
  advisory stating the plain suspension risk — the owner's informed choice,
  recorded in `audit/tos_acknowledgments.jsonl`.
- **Reddit:** automated upvoting is vote manipulation — **prohibited**. Bots
  are otherwise welcome where non-spammy and subreddit-rule-compliant.
- **YouTube:** automated outreach is spam (no creator DM feature) —
  **prohibited**; fake engagement of any kind is banned.
- **LinkedIn:** scraping/crawling and unauthorized automation are prohibited by the User Agreement — automated likes, comments, follows/connects, reshares, DMs, and browser-based data collection are **prohibited** (fail closed; `tos.acknowledged_risk: [linkedin]` opt-in only). Posting is drafts-for-human-approval; comment moderation on own posts is allowed.
- **TikTok / Instagram / Facebook:** automation without the platform's
  permission is prohibited in the literal terms; this tool's posture is
  human-directed, low-volume, own-account operation with the constraint shown
  on every guarded call. Bulk/spammy automation stays refused by the tool's
  own anti-spam guards.

These summaries are not legal advice; the official documents govern, and they
change over time — each file records its last-checked date.
