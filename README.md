# hubaycsenge.github.io

Personal site for Csenge Hubay, published with GitHub Pages. The homepage carries
a short research statement and an **openable panel** — *WikiLLM* — that expands
into a browsable, searchable rendering of the PhD research wiki.

## Raw materials are not in this repository

This is the constraint the build is designed around.

The wiki lives in a **separate, unpublished** vault at `../PhD_research`. That
vault has three layers:

| Layer | Contents | Published here? |
|---|---|---|
| `raw/` | Paper PDFs, scanned notes, cloned repos — 47 MB of third-party, mostly copyrighted material | **No.** Never read, never copied. |
| `wiki/` | The wiki's own prose, written about those sources | Yes, rendered to HTML. |
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
sentences, not the materials themselves. If you would rather they were not
public, the pages to look at are `wiki/log.html` and `wiki/citation-backlog.html`.

## Building

```sh
./build.sh                          # reads ../PhD_research, writes HTML here
./build.sh --vault ~/elsewhere      # different vault location
./build.sh --no-vault-pages         # publish wiki/** only, omitting the
                                    # vault's index.md catalogue and log.md
```

First run creates a gitignored `.venv` with `markdown` and `pyyaml`. The build is
fully static — there is no GitHub Action, and GitHub never sees the vault. Rerun
it whenever the wiki changes, then commit the regenerated HTML.

Preview locally:

```sh
python3 -m http.server 8765 && open http://127.0.0.1:8765/
```

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
- Emits `wiki/search.json`, a full-text index fetched lazily on the first
  keystroke. Before it loads — and on `file://` URLs — search still works over
  titles, summaries and tags.

Code blocks are shielded from link rewriting, so `[[…]]` inside a code sample
survives verbatim.

## Layout

```
index.html            generated homepage (do not edit by hand)
wiki/*.html           generated wiki pages
wiki/search.json      generated full-text index
wiki/pages.json       generated page manifest
content/home.md       ← EDIT THIS: bio, tagline, contact links, research themes
assets/style.css      hand-written
assets/site.js        hand-written
build.py, build.sh    the generator
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
Everything committed here is world-readable — which is why the vault stays out.
