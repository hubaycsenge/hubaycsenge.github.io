# hubaycsenge.github.io

Personal site for Csenge Hubay. It is two sites built from one generator:

- the **public homepage** (`index.html`), published with GitHub Pages. It holds the
  bio and research themes from `content/home.md` and a link to the wiki — nothing
  derived from the research vault;
- the **restricted wiki** — *WikiLLM*, a browsable, searchable rendering of the PhD
  research wiki — built into the gitignored `_private/` and served from
  Cloudflare Pages behind a GitHub sign-in, so only invited people can read it.

The public site links to the wiki through **`wikillm.html`**, a restricted-access
page with a *Sign in with GitHub* button (to `wiki_url`, where the sign-in turns
away anyone not on the reader list) and a
request-access email. Until `wiki_url` is set, the button shows as disabled.

A public **Student projects** page (`projects.html`) lists the topics offered to
students, grouped by course (AI lab, CI, EI). Each topic is a task specification:
description, background (why), and requirements for the finished system. It is
generated from `content/projects.yml` — edit that file, not the HTML. Each topic
also gets its own shareable page, `projects/<id>.html`, with a button that opens a
Teams chat about it (`teams_user`) and link-preview metadata; courses are told
apart by background tint (`color`). Like the homepage it contains nothing from the vault, so keep
unpublished results, participant data, collaborator names and host names out of it.

## Raw materials are not in this repository

This is the constraint the build is designed around.

The wiki lives in a **separate, unpublished** vault at `../PhD_research`. That
vault has three layers:

| Layer | Contents | Published? |
|---|---|---|
| `raw/` | Paper PDFs, scanned notes, cloned repos — 47 MB of third-party, mostly copyrighted material | **No.** Never read, never copied. |
| `wiki/` | The wiki's own prose, written about those sources | To invited readers only, rendered to HTML in `_private/`. |
| `CLAUDE.md` | Vault operating instructions | No. |

Four things enforce this:

1. `build.py` only walks `wiki/`, plus the vault's `index.md` and `log.md`. There
   is no code path that opens `raw/`.
2. `collect()` raises if any candidate path contains a `raw` component.
3. The `raw:` frontmatter field — which holds local filesystem paths into the
   source material — is stripped from every page before rendering.
4. `.gitignore` blocks `raw/`, `*.pdf`, `*.epub` and stray vault copies, as a
   second line of defence.

Note that wiki *prose* sometimes names a source file (`BartoSutton.pdf`) or
mentions the `raw/papers/` path when describing an ingest. Those are filenames in
sentences, not the materials themselves. If you would rather invited readers did
not see them either, the pages to look at are `wiki/log.html` and
`wiki/citation-backlog.html`.

## Building

```sh
./build.sh                          # reads ../PhD_research
./build.sh --vault ~/elsewhere      # different vault location
./build.sh --no-vault-pages         # omit the vault's index.md catalogue and log.md
```

One run writes both sites:

| Output | Contents | Goes to |
|---|---|---|
| `index.html` | public homepage, no vault content | GitHub (commit it) |
| `_private/` | the wiki only: `wiki/*.html`, `search.json`, `assets/` | Cloudflare (`./deploy-wiki.sh`) |

First run creates a gitignored `.venv` with `markdown` and `pyyaml`. There is no
GitHub Action, and GitHub never sees the vault or the rendered wiki. When the wiki
changes, rerun the build and `./deploy-wiki.sh`; commit only when `content/home.md`
or the generator changed.

Preview locally:

```sh
python3 -m http.server 8765 -d _private    # the wiki, at /wiki/
python3 -m http.server 8765                # the public homepage only
```

## The restricted wiki

GitHub Pages cannot restrict who reads a site (short of GitHub Enterprise Cloud),
so the wiki lives on **Cloudflare Pages** (free, no payment details) as project
`csenge-wiki`. In front of every request — pages, search index and assets —
runs `cloudflare/functions/_middleware.js`: visitors **sign in with GitHub**, and
only usernames in the `ALLOWED_GITHUB_USERS` secret get in. Others see a sign-in
page (401) or a not-authorised page (403). If any secret is missing it answers
503 for everything; it never falls back to serving the wiki. Sessions last 7
days, and the reader list is re-checked on every request.

The deployment holds the wiki and nothing else: the homepage and the Student
projects page exist only on github.io, and the wiki's Home and Student projects
links go there. After sign-in, `/` redirects to `/wiki/`. `deploy-wiki.sh` refuses
to upload a `_private/` with anything besides `wiki/`, `assets/` and `robots.txt`.

The public `wikillm.html` page on github.io links to the sign-in.

### One-time setup

1. **Log wrangler in and create the project** (done for `csenge-wiki`):
   ```sh
   npx wrangler@4 login
   npx wrangler@4 pages project create csenge-wiki --production-branch main --force
   ```
   `--force` is needed only here: without it, current wrangler creates a Workers
   project instead of a Pages one.
2. **Create a GitHub OAuth App** at GitHub → Settings → Developer settings →
   OAuth Apps → *New OAuth App*:
   - Homepage URL: `https://hubaycsenge.github.io`
   - Authorization callback URL: `https://csenge-wiki.pages.dev/auth/callback`

   Copy the *Client ID*, then *Generate a new client secret*.
3. **Set the four secrets** (each command prompts for the value):
   ```sh
   cd ~/Documents/hubaycsenge.github.io
   npx wrangler@4 pages secret put GITHUB_CLIENT_ID     --project-name csenge-wiki
   npx wrangler@4 pages secret put GITHUB_CLIENT_SECRET --project-name csenge-wiki
   npx wrangler@4 pages secret put ALLOWED_GITHUB_USERS --project-name csenge-wiki   # e.g. hubaycsenge, alice, bob
   openssl rand -hex 32 | npx wrangler@4 pages secret put SESSION_SECRET --project-name csenge-wiki
   ```
4. **Deploy:** `./build.sh && ./deploy-wiki.sh`. The script refuses to upload if
   the project or a secret is missing, and afterwards checks that signed-out
   requests get 401.
5. `wiki_url: "https://csenge-wiki.pages.dev"` in `content/home.md` turns on the
   *Sign in with GitHub* button on `wikillm.html`; rebuild, commit, push.

### Granting and revoking access

Put the new list into `ALLOWED_GITHUB_USERS` (step 3) and run `./deploy-wiki.sh`
— Pages applies secret changes to new deployments only. Removed users lose access
on their next request, even with a live session. To sign everyone out, replace
`SESSION_SECRET` and redeploy.

Test the sign-in locally, without GitHub, with
`cd cloudflare && npx wrangler@4 pages dev ../_private -b CANONICAL_HOST=127.0.0.1 -b …`
plus the four secrets as `-b NAME=value` bindings.

## What the build does

- Parses YAML frontmatter; renders `type`, `status`, `citekey`, `authors`,
  `year`, `venue`, `sources` and `tags` as a metadata block. `raw` is dropped.
- Resolves Obsidian `[[wikilinks]]` and `[[target|alias]]` against page
  filenames, which are globally unique in the vault. Unresolved links render as
  dotted-underlined text, not dead anchors — they mark future work, as in the
  vault itself.
- Converts Obsidian callouts (`> [!warning] …`) into styled blocks, so
  recorded contradictions between sources stay visually distinct.
- Computes **backlinks** for every page, shown under "Linked from".
- Emits `_private/wiki/search.json`, a full-text index fetched lazily on the first
  keystroke. Before it loads — and on `file://` URLs — search still works over
  titles, summaries and tags.

Code blocks are shielded from link rewriting, so `[[…]]` inside a code sample
survives verbatim.

## Layout

```
index.html            generated public homepage (do not edit by hand)
projects.html         generated public Student projects page
projects/*.html       generated public page per student project topic
wikillm.html          generated public WikiLLM sign-in / restricted page
_private/             generated restricted site — gitignored, deployed to Cloudflare
  wiki/*.html           wiki pages
  wiki/search.json      full-text index
  wiki/pages.json       page manifest
content/home.md       ← EDIT THIS: bio, tagline, contact links, wiki_url, research themes
content/projects.yml  ← EDIT THIS: student project topics, grouped by course
assets/style.css      hand-written
assets/site.js        hand-written
build.py, build.sh    the generator
cloudflare/functions/_middleware.js   GitHub sign-in in front of the wiki (Cloudflare Pages Functions)
deploy-wiki.sh        uploads _private/ with the sign-in to Cloudflare Pages
```

To change the homepage text, edit `content/home.md` and rebuild. Its frontmatter
holds your name, tagline, affiliation and contact links; blank fields are hidden.

## Publishing

The repository must be named `hubaycsenge.github.io` for a GitHub user site.

```sh
git remote add origin git@github.com:hubaycsenge/hubaycsenge.github.io.git
git push -u origin main
```

Then in the repository's **Settings → Pages**, set the source to *Deploy from a
branch*, branch `main`, folder `/ (root)`. The site appears at
<https://hubaycsenge.github.io> within a minute or two.

A user site repository must be **public** for Pages to serve it on a free plan.
Everything committed here is world-readable — which is why both the vault and the
rendered wiki stay out. `.gitignore` blocks `_private/`, `wiki/` and the JSON
indexes as a second line of defence.

The wiki was public here until September 2026; the repository history was
rewritten then to remove every rendered wiki page.
