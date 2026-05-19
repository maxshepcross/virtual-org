# 15 To Follow

Small web app for running a "pick 15 horses for the season" competition.

- **Entrants** pick 15 horses from a curated pool via a public form.
- **Admins** add horses, add races, and enter 1st/2nd/3rd.
- **10 / 5 / 3 points** are awarded for 1st / 2nd / 3rd whenever a picked horse places in a qualifying race.
- The leaderboard, alphabetical horse list, and per-horse "who picked this?" view all update automatically.

> This is a prototype living inside the `virtual-org` workspace under
> `prototypes/horse-racing-scorer/`. Before going live, **extract it to its own
> repo** (e.g. `maxshepcross/horse-comp`). It does not belong to the studio
> operations codebase long-term.

## Stack

- Next.js 16 (App Router) + React 19 + TypeScript
- Tailwind CSS v4
- SQLite via `better-sqlite3` (the database file lives in `data/comp.db`, which is gitignored)

## Local setup

```bash
cd prototypes/horse-racing-scorer
npm install
cp .env.example .env
# edit .env and set ADMIN_PASSWORD to something unguessable
npm run seed         # loads the 20 starter horses
npm run dev          # http://localhost:3000
```

Visit:

- `/` — landing
- `/enter` — entrants pick their 15
- `/leaderboard` — live ranking
- `/horses` — alphabetical pool
- `/horses/<slug>` — who picked this horse + its results
- `/admin/login` — sign in with `ADMIN_PASSWORD`
- `/admin` — add horses, manage races, enter results

## Loading the real horse pool

Drop a one-name-per-line file at `data/horses.txt` and re-run `npm run seed`.
Existing horses are skipped (matched on name), so it's safe to re-run.

```
data/horses.txt:

Auguste Rodin
City Of Troy
Constitution Hill
…
```

You can also bulk-paste from the admin UI under **Admin → Horses**.

## Scoring

Defined in `lib/scoring.ts`:

```ts
1st → 10 pts
2nd →  5 pts
3rd →  3 pts
```

Edit those numbers and restart.

## Auto-pulling results

Hooked up to [The Racing API](https://www.theracingapi.com/) (free plan,
covers UK + IRE results — what we need). Sync flow:

1. `npm run sync` (or the nightly cron) calls `GET /v1/results` for a date.
2. For each race's 1st/2nd/3rd, we fuzzy-match the horse name against the
   pool. Exact matches and high-confidence (~90%+) fuzzy matches apply
   immediately. Anything weaker goes to **Admin → Sync** as an "unmatched"
   row with a best-guess suggestion.
3. Idempotent: re-running the same date won't double-count (races are deduped
   by `external_id`, results by `(race_id, position)`).

### One-off / debugging

```bash
# Pull yesterday's results
npm run sync

# Pull a specific date
npm run sync -- --date 2026-05-14

# Dry-run: hit the API and match, but don't write anything
npm run sync -- --date 2026-05-14 --dry-run
```

Env vars required:

- `RACING_API_USERNAME` — from your dashboard at theracingapi.com
- `RACING_API_PASSWORD` — same

### Scheduling on Railway

Create a **second Railway service** in the same project pointing at the same
repo (root directory `prototypes/horse-racing-scorer`) with:

- **Start command:** `npm run sync -- --yesterday`
- **Cron schedule:** `15 6 * * *` (06:15 UTC — after results have settled overnight)
- **Variables:** same `RACING_API_USERNAME` / `RACING_API_PASSWORD`,
  same `DB_PATH=/app/data/comp.db`
- **Volume:** mount the **same** volume at `/app/data` (so the cron job writes
  to the same SQLite file the web service reads). In Railway: Volumes → Use
  Existing Volume → pick the web service's volume.

Then check `/admin/sync` each morning to clear any unmatched horses.

## Deploying

### Railway (recommended for this prototype)

Railway runs the whole thing as a single container with a persistent volume for
the SQLite file. ~£4/mo, no code changes from local dev.

1. Sign in at [railway.app](https://railway.app) (GitHub auth is fine).
2. **New Project → Deploy from GitHub repo → `maxshepcross/virtual-org`.**
3. In the service that gets created, open **Settings**:
   - **Root Directory:** `prototypes/horse-racing-scorer`
   - **Build Command:** leave blank (auto-detected)
   - **Start Command:** leave blank (auto-detected: `npm run start`)
4. Open **Variables** and add:
   - `ADMIN_PASSWORD` = something only you know
   - `DB_PATH` = `/app/data/comp.db`
   - `NODE_ENV` = `production`
5. Open **Volumes** → **New Volume**, mount it at `/app/data` (1 GB is plenty).
6. Deploy. On first request the DB schema bootstraps itself and the 20 starter
   horses auto-seed.
7. Open **Settings → Networking → Generate Domain** to get a public URL like
   `horse-comp-production.up.railway.app`. Share that.
8. Visit `/admin/login`, sign in with `ADMIN_PASSWORD`, paste the real horse
   list under **Admin → Horses** when you have it.

> The volume mount is the only non-obvious bit: without it, the SQLite file
> lives on ephemeral container disk and resets on every deploy. With the volume
> at `/app/data` and `DB_PATH=/app/data/comp.db`, the DB persists across deploys
> and restarts.

### Alternatives

- **Vercel + hosted Postgres**: swap `lib/db.ts` to use a Postgres adapter
  (e.g. `@neondatabase/serverless`) and translate the schema in `initSchema()`.
  The query layer in `lib/queries.ts` is small and easy to port. Worth it if
  you outgrow ~10k entries; not needed for a 150-person friends comp.
- **Fly.io**: same shape as Railway — single container + volume. CLI-heavier
  but free tier is generous.
- **Any VPS**: `next build && next start` with the SQLite file on persistent
  disk.

Either way, set:

- `ADMIN_PASSWORD` — required, gates `/admin/*`
- `DB_PATH` — path to the SQLite file (use the volume mount path)
- `RACING_API_USERNAME` / `RACING_API_PASSWORD` — required for the results sync
- `SKIP_AUTOSEED=1` — optional, disables the 20-horse autoseed if you want a
  fully blank pool

## Limitations / known follow-ups

- No email verification — anyone with someone else's email can overwrite their
  picks. Fine for a friends comp; add magic-link auth before opening it wider.
- No entry deadline enforcement — the form accepts submissions any time.
  Add a `Settings.entryDeadline` row and gate `/enter` on it.
- Per-horse races aren't tagged as "qualifying" — every race you add counts.
  If you want only Group 1s/Festivals to score, add a boolean to `race` and
  filter in `getLeaderboard`.
- Admin password is compared in plain text against a cookie. Fine for a friends
  comp on HTTPS; not fine if you're worried about real attackers.

## File map

```
app/
  layout.tsx, page.tsx          # public shell + landing
  enter/                        # entry form (client) + server action
  leaderboard/                  # live ranking
  horses/                       # alphabetical pool + per-horse view
  admin/
    login/                      # sign in (no auth required)
    actions.ts                  # signOut server action
    (authed)/                   # everything inside this group is auth-gated
      layout.tsx                # checks admin cookie, redirects if missing
      page.tsx                  # admin dashboard
      horses/                   # add/bulk-add/delete horses
      races/                    # create races + enter results
      entrants/                 # view all entries
lib/
  db.ts                         # better-sqlite3 connection + schema bootstrap
  queries.ts                    # all SQL lives here
  scoring.ts                    # 10/5/3 points table
  auth.ts                       # admin cookie helpers
scripts/
  seed.ts                       # reads data/horses.txt or starter list
```
