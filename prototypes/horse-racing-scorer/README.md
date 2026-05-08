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

## Auto-pulling results (future)

Results today are entered manually under **Admin → Races**. The schema is
already shaped for an automated feed:

- `race` rows define which races count.
- `result` rows record the top 3 horses per race.

A scraper or feed adapter just needs to upsert `race` + `result` rows and call
`revalidatePath('/leaderboard')`. Sources to consider: Racing Post,
At The Races, Sporting Life, BHA. Keep this out of the public web app — run it
as a scheduled job or a small CLI script that writes directly to the DB.

## Deploying

Two paths:

1. **Vercel + a hosted DB** (recommended for production):
   swap `lib/db.ts` to use a Postgres adapter (e.g. `@neondatabase/serverless`)
   and translate the schema in `initSchema()`. The query layer in
   `lib/queries.ts` is small and easy to port.

2. **A single VPS or Fly Volume**: `next build && next start` with the SQLite
   file on persistent disk. Fine for 150 entrants.

Either way, set:

- `ADMIN_PASSWORD` — required, gates `/admin/*`
- `DB_PATH` — optional, defaults to `./data/comp.db`

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
