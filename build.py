#!/usr/bin/env python3
"""
Static site generator for hubaycsenge.github.io.

Reads the PhD research vault's *prose* layer only — `wiki/**/*.md`, plus the
vault's own `index.md` and `log.md` — and renders it to standalone HTML in this
repository. The vault's `raw/` directory (paper PDFs, scanned notes, cloned
repos) is never opened, never copied and never referenced in the output; see
README.md and .gitignore.

Usage:
    ./build.sh                       # bootstraps a venv, then runs this
    python3 build.py --vault ~/Documents/PhD_research
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import markdown
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("Missing dependencies. Run ./build.sh, or: pip install markdown pyyaml")

SITE = Path(__file__).resolve().parent
DEFAULT_VAULT = SITE.parent / "PhD_research"

# Directories under the vault that hold prose we are allowed to publish.
# `raw/` is deliberately absent and is asserted against below.
PUBLISHABLE = ("wiki",)
VAULT_ROOT_PAGES = {"index.md": "catalog", "log.md": "log"}

CATEGORY_ORDER = [
    "synthesis",
    "sources",
    "models",
    "concepts",
    "methods",
    "systems",
    "datasets",
    "people",
    "experiments",
    "vault",
]

CATEGORY_META = {
    "synthesis": ("Synthesis", "The thesis argument, landscape maps, comparisons and open questions."),
    "sources": ("Sources", "One page per ingested source — the citation targets."),
    "models": ("Models", "Emotion and behaviour models treated as first-class objects."),
    "concepts": ("Concepts", "Ethology, affective computing and HRI concepts."),
    "methods": ("Methods", "Techniques, architectures and pipelines."),
    "systems": ("Systems", "Robot platforms, software stacks and ingested repositories."),
    "datasets": ("Datasets", "Emotion and behaviour corpora and benchmarks."),
    "people": ("People", "Researchers and labs."),
    "experiments": ("Experiments", "Own studies — design, status and results."),
    "vault": ("Vault", "The wiki's own catalogue and chronological research log."),
}

STATUS_BLURB = {
    "stub": "named, barely populated",
    "draft": "real content from at least one source, gaps remain",
    "solid": "well supported and cross-referenced",
}

# Frontmatter keys that must never reach the published page. `raw` holds local
# filesystem paths into the unpublished source material.
PRIVATE_FIELDS = {"raw"}

WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]*?))?\]\]")
CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\]([+-]?)\s*(.*)$")
FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)")


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


@dataclass
class Page:
    stem: str
    slug: str
    category: str
    title: str
    meta: dict
    body: str
    summary: str = ""
    text: str = ""
    html: str = ""
    outlinks: set[str] = field(default_factory=set)
    backlinks: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"wiki/{self.slug}.html"

    @property
    def status(self) -> str:
        return str(self.meta.get("status", "") or "")

    @property
    def tags(self) -> list[str]:
        raw = self.meta.get("tags") or []
        if isinstance(raw, str):
            raw = [t.strip() for t in raw.split(",")]
        return [str(t) for t in raw if str(t).strip()]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def split_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, parts[2].lstrip("\n")


def protect_code(text: str) -> tuple[str, list[str]]:
    """Replace fenced blocks and inline code with placeholders so that link and
    callout rewriting cannot corrupt code samples."""
    stash: list[str] = []
    out: list[str] = []
    fence: str | None = None
    buf: list[str] = []

    for line in text.split("\n"):
        if fence is None:
            m = FENCE_RE.match(line)
            if m:
                fence = m.group(2)[0] * 3
                buf = [line]
                continue
            out.append(line)
        else:
            buf.append(line)
            if line.strip().startswith(fence):
                stash.append("\n".join(buf))
                out.append(f"\x00CODE{len(stash) - 1}\x00")
                fence = None
                buf = []
    if fence is not None:  # unterminated fence — keep verbatim
        stash.append("\n".join(buf))
        out.append(f"\x00CODE{len(stash) - 1}\x00")

    joined = "\n".join(out)

    def stash_inline(m: re.Match) -> str:
        stash.append(m.group(0))
        return f"\x00CODE{len(stash) - 1}\x00"

    joined = re.sub(r"`[^`\n]+`", stash_inline, joined)
    return joined, stash


def restore_code(text: str, stash: list[str]) -> str:
    return re.sub(r"\x00CODE(\d+)\x00", lambda m: stash[int(m.group(1))], text)


def convert_callouts(text: str) -> str:
    """Obsidian callouts -> divs that the markdown extension `md_in_html` will
    still process as markdown."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = CALLOUT_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue

        kind, _fold, title = m.group(1).lower(), m.group(2), m.group(3).strip()
        i += 1
        body: list[str] = []
        while i < len(lines) and lines[i].startswith(">"):
            body.append(re.sub(r"^>\s?", "", lines[i]))
            i += 1

        out.append(f'<div class="callout callout-{html.escape(kind)}" markdown="1">')
        label = title or kind.capitalize()
        out.append(f'<p class="callout-title" markdown="1">{label}</p>')
        out.extend(body)
        out.append("</div>")
        out.append("")
    return "\n".join(out)


def prettify(stem: str) -> str:
    return stem.replace("-", " ").replace("_", " ").strip().capitalize()


def plain_text(md_body: str) -> str:
    """Rough plain-text projection, used for summaries and the search filter."""
    t = md_body
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), t)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[`*_>#|]+", " ", t)
    t = re.sub(r"^\s*[-+]{3,}\s*$", " ", t, flags=re.M)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def first_paragraph(md_body: str) -> str:
    for block in re.split(r"\n\s*\n", md_body):
        block = block.strip()
        if not block or block.startswith(("#", ">", "|", "-", "*", "```", "<")):
            continue
        text = plain_text(block)
        if len(text) > 30:
            return text
    return plain_text(md_body)[:400]


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut).rstrip(" ,;:") + "…"


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------


def collect(vault: Path, include_vault_pages: bool = True) -> list[Page]:
    pages: list[Page] = []
    seen: dict[str, Path] = {}

    candidates: list[tuple[Path, str, str]] = []
    for sub in PUBLISHABLE:
        root = vault / sub
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            rel = path.relative_to(root)
            category = rel.parts[0] if len(rel.parts) > 1 else "vault"
            candidates.append((path, path.stem, category))

    if include_vault_pages:
        for filename, slug in VAULT_ROOT_PAGES.items():
            path = vault / filename
            if path.is_file():
                candidates.append((path, slug, "vault"))

    for path, slug, category in candidates:
        # Hard guard: nothing from the raw layer may ever be read.
        if "raw" in path.relative_to(vault).parts:
            raise SystemExit(f"refusing to publish from the raw layer: {path}")

        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        stem = path.stem

        heading = re.search(r"^#\s+(.+)$", body, flags=re.M)
        title = heading.group(1).strip() if heading else prettify(stem)
        # The H1 is rendered from the title block instead, to avoid duplication.
        if heading:
            body = body[: heading.start()] + body[heading.end() :]

        if slug in seen:
            print(f"  ! slug collision: {slug} ({path} vs {seen[slug]})", file=sys.stderr)
        seen[slug] = path

        text = plain_text(body)
        pages.append(
            Page(
                stem=stem,
                slug=slug,
                category=category,
                title=title,
                meta={k: v for k, v in meta.items() if k not in PRIVATE_FIELDS},
                body=body,
                summary=truncate(first_paragraph(body), 220),
                text=truncate(text, 3000),
            )
        )
    return pages


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render_bodies(pages: list[Page]) -> None:
    by_stem = {p.stem: p for p in pages}
    by_slug = {p.slug: p for p in pages}
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "md_in_html", "footnotes"],
        output_format="html5",
    )

    for page in pages:
        source, stash = protect_code(page.body)
        source = convert_callouts(source)

        def link(m: re.Match, _page: Page = page) -> str:
            target, alias = m.group(1).strip(), (m.group(2) or "").strip()
            anchor = ""
            if "#" in target:
                target, _, anchor_txt = target.partition("#")
                target, anchor = target.strip(), "#" + re.sub(r"[^\w-]+", "-", anchor_txt.strip().lower())
            target = re.sub(r"\.md$", "", target)
            label = html.escape(alias or m.group(1).strip())
            hit = by_stem.get(target) or by_slug.get(target)
            if not hit:
                hit = by_stem.get(target.lower()) or by_slug.get(target.lower())
            if hit:
                _page.outlinks.add(hit.slug)
                return f'<a class="wikilink" href="{hit.slug}.html{anchor}">{label}</a>'
            return (
                f'<span class="wikilink-missing" title="No page for “{html.escape(target)}” yet">'
                f"{label}</span>"
            )

        source = WIKILINK_RE.sub(link, source)

        def mdlink(m: re.Match) -> str:
            """Ordinary [label](target.md) links point at vault files. Retarget
            them if the file is published; otherwise keep the label and drop the
            link rather than emitting a 404 into the vault."""
            label, target = m.group(1), m.group(2)
            if re.match(r"^[a-z]+:", target):
                return m.group(0)
            stem = Path(target.split("#")[0]).stem
            hit = by_stem.get(stem) or by_slug.get(stem)
            return f"[{label}]({hit.slug}.html)" if hit else label

        source = re.sub(r"\[([^\]]+)\]\(([^)\s]+\.md(?:#[^)\s]*)?)\)", mdlink, source)
        source = restore_code(source, stash)

        md.reset()
        page.html = md.convert(source)

    for page in pages:
        for slug in page.outlinks:
            if slug != page.slug:
                by_slug[slug].backlinks.append(page.slug)
    for page in pages:
        page.backlinks = sorted(set(page.backlinks), key=lambda s: by_slug[s].title.lower())


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------


def shell(*, title: str, description: str, body: str, depth: int, active: str, extra_head: str = "") -> str:
    up = "../" if depth else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="stylesheet" href="{up}assets/style.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🐕</text></svg>">
{extra_head}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar">
  <a class="brand" href="{up}index.html">Csenge Hubay</a>
  <nav>
    <a href="{up}index.html"{' class="on"' if active == "home" else ""}>Home</a>
    <a href="{up}wiki/index.html"{' class="on"' if active == "wiki" else ""}>Research wiki</a>
  </nav>
</header>
<main id="main">
{body}
</main>
<footer class="foot">
  <p>Csenge Hubay · <a href="mailto:csengehubay@gmail.com">csengehubay@gmail.com</a></p>
  <p class="fine">Wiki prose is generated from a private research vault. The underlying
  sources — paper PDFs and unpublished notes — are not published here.</p>
</footer>
<script src="{up}assets/site.js" defer></script>
</body>
</html>
"""


def badge(status: str) -> str:
    if not status:
        return ""
    blurb = STATUS_BLURB.get(status, "")
    return f'<span class="badge badge-{html.escape(status)}" title="{html.escape(blurb)}">{html.escape(status)}</span>'


def card(page: Page, prefix: str = "") -> str:
    # Only light metadata is inlined; full page text is fetched lazily from
    # search.json on the first keystroke, so the page stays small.
    haystack = " ".join([page.title, page.summary, " ".join(page.tags), page.category]).lower()
    return f"""<a class="card" href="{prefix}{page.slug}.html" data-slug="{html.escape(page.slug)}"
   data-search="{html.escape(haystack, quote=True)}"
   data-status="{html.escape(page.status)}" data-category="{html.escape(page.category)}">
  <span class="card-head"><span class="card-title">{html.escape(page.title)}</span>{badge(page.status)}</span>
  <span class="card-sum">{html.escape(page.summary)}</span>
</a>"""


def grouped(pages: list[Page]) -> list[tuple[str, list[Page]]]:
    buckets: dict[str, list[Page]] = {}
    for p in pages:
        buckets.setdefault(p.category, []).append(p)
    order = CATEGORY_ORDER + sorted(set(buckets) - set(CATEGORY_ORDER))
    out = []
    for cat in order:
        if cat in buckets:
            out.append((cat, sorted(buckets[cat], key=lambda p: p.title.lower())))
    return out


def browser_markup(pages: list[Page], prefix: str, id_prefix: str) -> str:
    """The search box + category listing shared by the homepage panel and the
    wiki index page."""
    blocks = []
    for cat, items in grouped(pages):
        label, blurb = CATEGORY_META.get(cat, (cat.capitalize(), ""))
        cards = "\n".join(card(p, prefix) for p in items)
        blocks.append(f"""<section class="catblock" data-cat="{html.escape(cat)}">
  <h3 class="cat-h">{html.escape(label)} <span class="cat-n">{len(items)}</span></h3>
  <p class="cat-blurb">{html.escape(blurb)}</p>
  <div class="cards">
{cards}
  </div>
</section>""")

    return f"""<div class="browser" data-browser data-index="{prefix}search.json">
  <div class="searchrow">
    <input type="search" id="{id_prefix}-q" class="search" data-search-input
           placeholder="Search {len(pages)} pages — titles, summaries, tags, contents…"
           autocomplete="off" aria-label="Search the wiki">
    <div class="filters" role="group" aria-label="Filter by status">
      <button type="button" class="chip on" data-filter="all">All</button>
      <button type="button" class="chip" data-filter="solid">solid</button>
      <button type="button" class="chip" data-filter="draft">draft</button>
      <button type="button" class="chip" data-filter="stub">stub</button>
    </div>
  </div>
  <p class="hits" data-hits aria-live="polite"></p>
{"".join(blocks)}
  <p class="noresults" data-noresults hidden>No page matches that.</p>
</div>"""


def render_home(cfg: dict, about_html: str, pages: list[Page]) -> str:
    name = cfg.get("name", "Csenge Hubay")
    tagline = cfg.get("tagline", "")
    affiliation = (cfg.get("affiliation") or "").strip()
    sources = max((int(p.meta.get("sources") or 0) for p in pages), default=0)
    n_sources = len([p for p in pages if p.category == "sources"])
    solid = len([p for p in pages if p.status == "solid"])

    links = []
    if cfg.get("email"):
        links.append(f'<a href="mailto:{html.escape(cfg["email"])}">{html.escape(cfg["email"])}</a>')
    if cfg.get("github"):
        links.append(f'<a href="https://github.com/{html.escape(cfg["github"])}">GitHub</a>')
    if cfg.get("scholar"):
        links.append(f'<a href="{html.escape(cfg["scholar"])}">Google Scholar</a>')
    if cfg.get("orcid"):
        links.append(f'<a href="{html.escape(cfg["orcid"])}">ORCID</a>')

    aff = f'<p class="aff">{html.escape(affiliation)}</p>' if affiliation else ""

    body = f"""<section class="hero">
  <h1>{html.escape(name)}</h1>
  <p class="tagline">{html.escape(tagline)}</p>
  {aff}
  <p class="links">{" · ".join(links)}</p>
</section>

<section class="prose about">
{about_html}
</section>

<details class="wikifield" id="wikillm">
  <summary>
    <span class="wf-text">
      <span class="wf-eyebrow">Doctoral research · open to browse</span>
      <span class="wf-title">WikiLLM — the PhD research wiki</span>
      <span class="wf-desc">A living, LLM-maintained wiki on emotion modelling for social
      robots. Every factual claim is traceable to an ingested source; disagreements between
      sources are recorded rather than resolved. {len(pages)} pages, {n_sources} sources
      ingested, {solid} rated solid.</span>
    </span>
    <span class="wf-cue" aria-hidden="true"><span class="wf-open">Open</span><span class="wf-close">Close</span></span>
  </summary>
  <div class="wf-body">
    <div class="wf-stats">
      <div class="stat"><b>{len(pages)}</b><span>pages</span></div>
      <div class="stat"><b>{n_sources}</b><span>sources ingested</span></div>
      <div class="stat"><b>{solid}</b><span>solid</span></div>
      <div class="stat"><b>{len([p for p in pages if p.status == "draft"])}</b><span>draft</span></div>
    </div>
    <p class="wf-note">The wiki is a working document, not a publication. Status labels are
    honest: <em>stub</em> means barely populated, <em>draft</em> means real content with gaps,
    <em>solid</em> means it would survive a supervisor reading it. Source PDFs and unpublished
    notes stay in a private vault — only the wiki's own prose is published.</p>
{browser_markup(pages, "wiki/", "home")}
    <p class="wf-more"><a class="btn" href="wiki/index.html">Open the full wiki →</a></p>
  </div>
</details>
"""
    desc = f"{name} — {tagline}. Ethorobotics, emotion modelling for social robots, and an open research wiki."
    return shell(title=f"{name} — {tagline}", description=desc, body=body, depth=0, active="home")


def render_wiki_index(pages: list[Page]) -> str:
    body = f"""<section class="prose pagehead">
  <p class="crumb"><a href="../index.html">Home</a> / Research wiki</p>
  <h1>Research wiki</h1>
  <p class="lede">Emotion modelling for social robots, in the ethorobotics tradition.
  {len(pages)} pages maintained as sources are ingested. Every claim is cited to a source
  page; unsourced background is marked as such on the page where it appears.</p>
  <p class="fine">The raw layer — paper PDFs and unpublished notes — is not published.
  Source pages describe and cite their material rather than reproducing it.</p>
</section>
{browser_markup(pages, "", "wiki")}
"""
    return shell(
        title="Research wiki — Csenge Hubay",
        description="An LLM-maintained research wiki on emotion modelling for social robots.",
        body=body,
        depth=1,
        active="wiki",
    )


def meta_rows(page: Page) -> str:
    rows = []
    order = ["type", "status", "citekey", "authors", "year", "venue", "sources", "created", "updated"]
    for key in order:
        if key not in page.meta:
            continue
        val = page.meta[key]
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        if val in ("", None):
            continue
        shown = badge(str(val)) if key == "status" else html.escape(str(val))
        rows.append(f"<div><dt>{html.escape(key)}</dt><dd>{shown}</dd></div>")
    if page.tags:
        tags = " ".join(f'<span class="tag">{html.escape(t)}</span>' for t in page.tags)
        rows.append(f"<div><dt>tags</dt><dd>{tags}</dd></div>")
    return f'<dl class="meta">{"".join(rows)}</dl>' if rows else ""


def render_page(page: Page, by_slug: dict[str, Page]) -> str:
    label = CATEGORY_META.get(page.category, (page.category.capitalize(), ""))[0]

    backlinks = ""
    if page.backlinks:
        items = "\n".join(
            f'<li><a href="{by_slug[s].slug}.html">{html.escape(by_slug[s].title)}</a></li>'
            for s in page.backlinks
        )
        backlinks = f"""<section class="backlinks">
  <h2>Linked from</h2>
  <ul>{items}</ul>
</section>"""

    body = f"""<article class="prose page">
  <p class="crumb"><a href="../index.html">Home</a> / <a href="index.html">Research wiki</a> / {html.escape(label)}</p>
  <h1>{html.escape(page.title)}</h1>
{meta_rows(page)}
{page.html}
{backlinks}
</article>"""
    return shell(
        title=f"{page.title} — Research wiki",
        description=truncate(page.summary, 155),
        body=body,
        depth=1,
        active="wiki",
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT, help="path to the PhD_research vault")
    ap.add_argument(
        "--no-vault-pages",
        action="store_true",
        help="publish only wiki/**, omitting the vault's own index.md catalogue and log.md chronology",
    )
    args = ap.parse_args()

    vault = args.vault.expanduser().resolve()
    if not (vault / "wiki").is_dir():
        return print(f"No wiki/ under {vault}", file=sys.stderr) or 1

    print(f"vault  {vault}")
    print(f"output {SITE}")

    cfg, about_md = split_frontmatter((SITE / "content" / "home.md").read_text(encoding="utf-8"))
    about_html = markdown.Markdown(extensions=["tables", "sane_lists", "attr_list"]).convert(about_md)

    pages = collect(vault, include_vault_pages=not args.no_vault_pages)
    if not pages:
        return print("No pages found.", file=sys.stderr) or 1
    render_bodies(pages)
    by_slug = {p.slug: p for p in pages}

    out_wiki = SITE / "wiki"
    if out_wiki.exists():
        shutil.rmtree(out_wiki)
    out_wiki.mkdir(parents=True)

    for page in pages:
        (out_wiki / f"{page.slug}.html").write_text(render_page(page, by_slug), encoding="utf-8")
    (out_wiki / "index.html").write_text(render_wiki_index(pages), encoding="utf-8")
    (SITE / "index.html").write_text(render_home(cfg, about_html, pages), encoding="utf-8")

    (out_wiki / "pages.json").write_text(
        json.dumps(
            [
                {"slug": p.slug, "title": p.title, "category": p.category, "status": p.status, "url": p.url}
                for p in sorted(pages, key=lambda p: p.title.lower())
            ],
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # Full-text haystack, fetched on demand by the search box.
    (out_wiki / "search.json").write_text(
        json.dumps({p.slug: p.text.lower() for p in pages}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    unresolved = sum(len(re.findall(r"wikilink-missing", p.html)) for p in pages)
    orphans = [p.slug for p in pages if not p.backlinks and p.category != "vault"]
    print(f"\n{len(pages)} pages rendered across {len(grouped(pages))} categories")
    print(f"  unresolved wikilinks: {unresolved}")
    if orphans:
        print(f"  orphans (no inbound links): {', '.join(orphans)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
