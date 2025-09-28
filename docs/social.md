# Social Service

The social service powers public profiles, follow relationships, activity feeds
and performance leaderboards. Access is mediated through entitlements and every
state change is persisted to the shared audit trail.

## Database schema

| Table | Description |
| --- | --- |
| `social_profiles` | Public profile for each user (display name, bio, visibility). |
| `social_follows` | Directed follow relationships between users. |
| `social_activities` | Activity feed entries (follow events, manual posts, etc.). |
| `social_leaderboards` | Snapshots of curated leaderboards. |
| `audit_logs` | Central audit trail storing social events. |

## Entitlements

- `can.publish_strategy` – required to manage your profile, post activities and
  maintain leaderboards.
- `can.copy_trade` – required to follow another profile.

The FastAPI app expects an `X-User-Id` (or `X-Customer-Id`) header to map
requests to entitlements.

## REST API

All endpoints live under the `/social` prefix.

### Profiles

- `PUT /social/profiles/me` — create or update the authenticated user's public
  profile.
- `GET /social/profiles/{user_id}` — fetch a public profile. Private profiles are
  hidden unless requested by their owner.

### Follows

`POST /social/follows` toggles follow status. Set `{"follow": false}` to
unfollow. Follow actions automatically emit both activity feed entries and audit
logs.

### Activity feed

- `POST /social/activities` — create a custom activity entry (for example a
  shared trade or a milestone).
- `GET /social/activities` — fetch the latest activities for the authenticated
  user and the profiles they follow. The `limit` query parameter constrains the
  number of results (default 20).

### Leaderboards

- `PUT /social/leaderboards/{slug}` — create or refresh a leaderboard snapshot.
- `GET /social/leaderboards/{slug}` — retrieve an existing leaderboard.

## Audit trail

Profile updates, follow/unfollow events, activity posts and leaderboard changes
write to `audit_logs`. The audit entries capture the service name, action code,
actors and contextual metadata to make compliance reviews simple.
