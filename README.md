# hubaycsenge.github.io

Personal site for Csenge Hubay. It is two sites built from one generator:

- the **public homepage** (`index.html`), published with GitHub Pages. It holds the
  bio and research themes from `content/home.md` and a link to the wiki — nothing
  derived from the research vault;
- the **restricted wiki** — *WikiLLM*, a browsable, searchable rendering of the PhD
  research wiki — built into the gitignored `_private/` and served from
  Cloudflare Pages behind Cloudflare Access, so only invited people can read it.

The public site links to the wiki through **`wikillm.html`**, a restricted-access
page with a *Sign in* button (to `wiki_url`, where Cloudflare Access asks for an
email and one-time code and turns away anyone not on the list) and a
request-access email. Until `wiki_url` is set, the button shows as disabled.

A public **Open projects** page (`projects.html`) lists work open to students and
collaborators. It is generated from `content/projects.yml` — edit that file, not
the HTML. Like the homepage it contains nothing from the vault, so keep
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
| `_private/` | homepage with the WikiLLM panel, `wiki/*.html`, `search.json`, `assets/` | Cloudflare (`./deploy-wiki.sh`) |

First run creates a gitignored `.venv` with `markdown` and `pyyaml`. There is no
GitHub Action, and GitHub never sees the vault or the rendered wiki. When the wiki
changes, rerun the build and `./deploy-wiki.sh`; commit only when `content/home.md`
or the generator changed.

Preview locally:

```sh
python3 -m http.server 8765 -d _private    # the full site, wiki included
python3 -m http.server 8765                # the public homepage only
```

## The restricted wiki

GitHub Pages cannot restrict who reads a site (short of GitHub Enterprise Cloud),
so the wiki lives on **Cloudflare Pages** and **Cloudflare Access** decides who may
open it. Access is free for up to 50 users. A reader visits the wiki URL, signs in
— with a one-time code sent to their email, or with GitHub if you enable that
login method — and gets in only if their email address is on your list.

### One-time setup

Do these in order: the deploy script refuses to upload until step 3 is in place.

1. **Log wrangler in and create the project** (the name becomes the URL):
   ```sh
   npx wrangler@4 login
   npx wrangler@4 pages project create csenge-wiki --production-branch main
   ```
   If `csenge-wiki` is taken, choose another name and export
   `WIKI_PROJECT=<name>` before running the deploy script.
2. **Open Zero Trust** in the Cloudflare dashboard and pick a team name (free plan).
3. **Access → Applications → Add an application → Self-hosted.**
   - Application domains: add **both** `csenge-wiki.pages.dev` **and**
     `*.csenge-wiki.pages.dev`. The wildcard covers per-deployment preview URLs,
     which otherwise stay publicly reachable.
   - Policy: action *Allow*, include *Emails* — list the people you permit.
     (*Emails ending in* `@inf.elte.hu` admits a whole domain; a *GitHub
     organization* rule is available once GitHub is a login method.)
   - Login methods: *One-time PIN* works with no further setup. For "Sign in
     with GitHub", add GitHub under *Settings → Authentication* first.
4. **Deploy:** `./deploy-wiki.sh`
5. Put the URL in `content/home.md` as `wiki_url`, rebuild, commit, push — the
   public homepage then links to it.

To grant or revoke access later, edit the emails in the Access policy. No
rebuild or redeploy needed.

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
projects.html         generated public Open projects page
wikillm.html          generated public WikiLLM sign-in / restricted page
_private/             generated restricted site — gitignored, deployed to Cloudflare
  index.html            homepage with the WikiLLM panel
  wiki/*.html           wiki pages
  wiki/search.json      full-text index
  wiki/pages.json       page manifest
content/home.md       ← EDIT THIS: bio, tagline, contact links, wiki_url, research themes
content/projects.yml  ← EDIT THIS: open projects and task descriptions
assets/style.css      hand-written
assets/site.js        hand-written
build.py, build.sh    the generator
deploy-wiki.sh        uploads _private/ to Cloudflare Pages, after checking Access
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
