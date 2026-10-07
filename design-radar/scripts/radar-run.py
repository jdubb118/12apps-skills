#!/usr/bin/env python3
"""
design-radar accumulator — grows the research library a little every week.

Two lanes:
  TECHNIQUES  Codrops RSS  -> references/ideas.md      (named, implementable things)
  EVIDENCE    Awwwards     -> references/corpus.md     (what actually ships) + trends

Fully deterministic: no LLM call, no API key, $0 per run. Only NEW items are
processed, so week 2 onward is cheap (a handful of renders).

Usage:  python3 radar-run.py [--max-render N] [--no-render] [--dry-run]
"""
import json, os, re, html, subprocess, sys, datetime, collections, urllib.request

SKILL = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
STATE = os.path.join(SKILL, "state")
REFS  = os.path.join(SKILL, "references")
INSPECT = os.path.join(SKILL, "scripts", "site-inspect.mjs")   # needs `npm install` in scripts/
SCRIPTS = os.path.dirname(INSPECT)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 design-radar/1.0"

MAX_RENDER = 12          # bound cost/time per run
DRY = "--dry-run" in sys.argv
# How far back the techniques lane will accept a Codrops post. The job runs
# weekly; this is wide enough to survive a missed run or two, narrow enough
# to reject the homepage's rotating evergreen block.
BACKFILL_DAYS = 45
NO_RENDER = "--no-render" in sys.argv
if "--max-render" in sys.argv:
    MAX_RENDER = int(sys.argv[sys.argv.index("--max-render") + 1])

SKIP_HOST = re.compile(
    r'(awwwards|w3\.org|instagram|linkedin|youtube|tiktok|pinterest|facebook|twitter'
    r'|x\.com|google|gstatic|googleapis|cloudflare|schema\.org|vimeo|behance|dribbble'
    r'|github|apple\.com|paypal|stripe|typekit|adobe|jsdelivr|unpkg|bit\.ly'
    r'|threads\.net|whatsapp|t\.me|medium\.com|substack)', re.I)


def log(*a): print(*a, flush=True)


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def load(name, default):
    p = os.path.join(STATE, name)
    if not os.path.exists(p):
        return default
    try:
        return json.load(open(p))
    except Exception:
        return default


def save(name, obj):
    if DRY:
        return
    os.makedirs(STATE, exist_ok=True)
    json.dump(obj, open(os.path.join(STATE, name), "w"), indent=1)


def strip(s):
    return " ".join(html.unescape(re.sub("<[^>]+>", "", s)).split())


# ---------------------------------------------------------------- lane 1: ideas
def article_meta(url):
    """Fetch a Codrops article once and pull title, description, demo + code URLs.

    The whole point of the ledger is being able to SHOW an example, so the demo
    URL matters more than the writeup. Failure here is non-fatal — we still log
    the article.

    ⚠️ Codrops KILLED its RSS feed (HTTP 410 Gone, confirmed 2026-09-22 on
    /feed/, /feed, ?feed=rss2 and /comments/feed/ — the site itself is 200).
    410 is deliberate and permanent, so the old feed parser can never recover.
    Title/description now come from og: meta on the article page, which is why
    this does the fetch that article_links() used to do.
    """
    out = {"title": "", "desc": "", "demo": "", "code": ""}
    try:
        x = html.unescape(get(url, timeout=25))
    except Exception:
        return out

    m = re.search(r'<meta property="og:title" content="([^"]*)"', x, re.I)
    if m:
        # WordPress appends " | Codrops" to every og:title
        out["title"] = re.sub(r"\s*\|\s*Codrops\s*$", "", strip(m.group(1)))
    m = re.search(r'<meta property="og:description" content="([^"]*)"', x, re.I)
    if m:
        out["desc"] = strip(m.group(1))[:260]

    # Category survives as a link in the body even though article:section is absent
    out["cats"] = {c.lower() for c in re.findall(
        r'href="https://tympanus\.net/codrops/category/([a-z0-9-]+)/"', x, re.I)}

    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]{0,40}?)\s*</a>', x, re.I):
        href, label = m.group(1), m.group(2).strip().lower()
        if not href.startswith("http"):
            continue
        # tutorials label it "Demo"; case-studies label the live site "Visit"
        if not out["demo"] and label in ("demo", "live demo", "view demo", "demos",
                                         "visit", "visit site", "website", "live site"):
            out["demo"] = href
        elif not out["code"] and label in ("code", "source", "github", "source code"):
            if "github.com/codrops" not in href:   # generic footer link, not the project
                out["code"] = href
    return out


def lane_techniques():
    """Codrops homepage -> new implementable techniques.

    Was RSS until 2026-09-20, when the feed started returning 410 Gone and the
    lane silently contributed nothing for a week. The homepage lists the same
    posts with the publish date embedded in each URL path, so it is a drop-in
    source that needs no feed.
    """
    seen = set(load("seen-articles.json", []))
    try:
        page = get("https://tympanus.net/codrops/")
    except Exception as e:
        log(f"  ! codrops fetch failed: {e}")
        return None                       # None = sensor dead, [] = quiet week

    # /codrops/YYYY/MM/DD/slug/ — dedup but keep the page's own ordering (newest first)
    links, order = set(), []
    for m in re.finditer(
            r"https://tympanus\.net/codrops/(20\d{2})/(\d{2})/(\d{2})/[a-z0-9-]+/", page):
        u = m.group(0)
        if u not in links:
            links.add(u)
            order.append((u, f"{m.group(1)}-{m.group(2)}-{m.group(3)}"))

    if not order:
        log("  ! codrops returned 0 articles — homepage shape may have changed")
        return None                       # None = sensor dead, [] = quiet week

    # ⚠️ The homepage is not a feed: alongside this week's posts it rotates a
    # block of evergreen "popular" articles. On 2026-09-22 ALL 6 unseen links
    # were 2025/early-2026 back catalogue. Without a window, every weekly run
    # drags ~6 archive posts into a ledger whose whole job is "what's new".
    cutoff = (datetime.date.today() - datetime.timedelta(days=BACKFILL_DAYS)).isoformat()

    fresh, stale = [], 0
    for link, date in order:
        if link in seen:
            continue
        if date < cutoff:
            stale += 1
            seen.add(link)            # remember it so we don't re-check every week
            continue
        meta = article_meta(link)
        if not meta["title"]:
            continue                      # fetch failed; retry on a later run
        cats = meta.get("cats") or set()
        # same acceptance set the RSS lane used; empty cats passes, as it did before
        if cats and not (cats & {"tutorials", "articles", "playground", "demos"}):
            continue                      # job posts / collective roundups
        fresh.append({"title": meta["title"], "link": link, "demo": meta["demo"],
                      "code": meta["code"], "date": date, "desc": meta["desc"]})
        seen.add(link)

    # The homepage also lists evergreen "popular" posts, so a run can pick up
    # old articles alongside this week's. append_ideas() prepends the block
    # verbatim, so sort newest-first or a 2025 post lands above September.
    fresh.sort(key=lambda a: a["date"], reverse=True)

    save("seen-articles.json", sorted(seen))
    log(f"  codrops: {len(order)} on homepage, {len(fresh)} new"
        + (f", {stale} evergreen skipped (>{BACKFILL_DAYS}d)" if stale else ""))
    return fresh


def append_ideas(fresh):
    if not fresh:                         # None (lane dead) or [] (nothing new)
        return
    p = os.path.join(REFS, "ideas.md")
    head = ("# Ideas Ledger — experimental techniques worth stealing\n\n"
            "Auto-accumulated from Codrops by `scripts/radar-run.py`. Newest first.\n"
            "Each entry is a *named, implementable* technique with a working writeup\n"
            "behind the link. Nothing here is applied to a project — it's the shelf.\n\n"
            "---\n")
    body = open(p).read() if os.path.exists(p) else head
    marker = "---\n"
    i = body.find(marker) + len(marker)
    block = ""
    for a in fresh:
        links = [f"[writeup]({a['link']})"]
        if a.get("demo"): links.insert(0, f"**[▶ live demo]({a['demo']})**")
        if a.get("code"): links.append(f"[code]({a['code']})")
        block += f"\n### {a['title']}\n`{a['date']}` · {' · '.join(links)}\n\n{a['desc']}\n"
    new = body[:i] + block + body[i:]
    if not DRY:
        open(p, "w").write(new)
    log(f"  ideas.md: +{len(fresh)} techniques")


# ------------------------------------------------------------- lane 2: evidence
def resolve_targets(limit):
    """New Awwwards SOTD slugs -> destination URLs."""
    seen = load("seen-sites.json", {})
    try:
        page = get("https://www.awwwards.com/websites/sites_of_the_day/")
    except Exception as e:
        log(f"  ! awwwards fetch failed: {e}")
        return {}, seen
    slugs = []
    for m in re.finditer(r'href="/sites/([a-z0-9\-]+)"', page):
        if m.group(1) not in slugs:
            slugs.append(m.group(1))
    if not slugs:
        log("  ! awwwards listing yielded 0 slugs — markup may have changed")
        return {}, seen
    new = [s for s in slugs if s not in seen][:limit]
    log(f"  awwwards: {len(slugs)} on page, {len([s for s in slugs if s not in seen])} new"
        f" (taking {len(new)})")
    out = {}
    for s in new:
        try:
            h = html.unescape(get(f"https://www.awwwards.com/sites/{s}", timeout=25))
        except Exception:
            continue
        c = collections.Counter()
        for m in re.finditer(r"https?://([a-z0-9.\-]+)", h):
            d = m.group(1)
            if SKIP_HOST.search(d) or d.count(".") > 3:
                continue
            c[d] += 1
        if c:
            out[s] = "https://" + c.most_common(1)[0][0]
    return out, seen


def render(targets):
    """Headless-render each new site. Returns slug -> inspection dict."""
    results = {}
    if not targets or NO_RENDER or DRY:
        return results
    if not os.path.exists(INSPECT):
        log(f"  ! missing {INSPECT} — skipping render lane")
        return results
    items = list(targets.items())
    for i in range(0, len(items), 4):
        procs = []
        for slug, url in items[i:i + 4]:
            procs.append((slug, subprocess.Popen(
                ["node", INSPECT, url, "--wait", "6000"], cwd=SCRIPTS,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)))
        for slug, p in procs:
            try:
                out, _ = p.communicate(timeout=150)
                d = json.loads(out.decode("utf-8", "replace"))
                if "error" not in d:
                    results[slug] = d
                    # persist the raw evidence so corpus.md can always be rebuilt
                    os.makedirs(os.path.join(STATE, "sites"), exist_ok=True)
                    json.dump(d, open(os.path.join(STATE, "sites", f"{slug}.json"), "w"))
            except Exception:
                try: p.kill()
                except Exception: pass
    log(f"  rendered {len(results)}/{len(targets)}")
    return results


def evidence_tags(d):
    a = {k: len(v) for k, v in (d.get("assets") or {}).items() if v}
    t = []
    if a.get("models"): t.append("3D")
    if a.get("compressedTextures"): t.append("KTX2")
    if a.get("hdrEnv"): t.append("HDR")
    if a.get("video"): t.append("video")
    if a.get("audio"): t.append("audio")
    if d.get("canvasCount"): t.append(f"canvas×{d['canvasCount']}")
    return ", ".join(t) or "—"


def rebuild_corpus():
    """Rebuild corpus.md from persisted evidence + seen-sites.json.

    URLs are written as bare visible text (not just hrefs) so an example can be
    quoted or opened straight from the table."""
    seen = load("seen-sites.json", {})
    sdir = os.path.join(STATE, "sites")
    rows = []
    for slug, meta in seen.items():
        url = meta.get("url", "")
        f = os.path.join(sdir, f"{slug}.json")
        title, stack, ev = slug.replace("-", " ").title(), "—", "not rendered"
        if os.path.exists(f):
            try:
                d = json.load(open(f))
                # a raw "|" in a page title silently forges an extra table column
                title = (d.get("title") or slug)[:40].replace("|", "\\|")
                st = [k for k, v in d.get("stack", {}).items() if v and k != "webgpu"]
                stack = ", ".join(st) or "—"
                ev = evidence_tags(d)
            except Exception:
                pass
        rows.append((meta.get("seen", ""), slug, title, url, stack, ev))
    rows.sort(key=lambda r: (r[0], r[2]), reverse=True)
    out = ["# Corpus — inspected award-winning sites", "",
           f"{len(rows)} sites. Each rendered headless (1440×900), scrolled, network +",
           "runtime captured. Rebuilt by `scripts/radar-run.py`.", "",
           "**Live URLs are listed in full so any of these can be opened or shown as an",
           "example on request.** `aw:` links back to the Awwwards write-up.", "",
           "| Site | Live URL | Stack (globals) | Evidence | Seen |",
           "|---|---|---|---|---|"]
    for seen_at, slug, title, url, stack, ev in rows:
        aw = f"https://www.awwwards.com/sites/{slug}"
        out.append(f"| **{title}**<br>[aw]({aw}) | <{url}> | {stack} | {ev} | {seen_at} |")
    out += ["", "## Reading this table", "",
            "`Stack (globals)` is **under-reported by design** — bundlers hide library",
            "globals. A row showing `—` alongside `3D, KTX2, HDR` is a heavy three.js",
            "site whose globals simply aren't exposed. Trust the Evidence column."]
    if not DRY:
        open(os.path.join(REFS, "corpus.md"), "w").write("\n".join(out) + "\n")
    log(f"  corpus.md: rebuilt, {len(rows)} sites")


def append_trends(results):
    """One history line per run — this is what makes the library longitudinal."""
    if not results:
        return
    keys = ["gsap", "ScrollTrigger", "Lenis", "barba", "next", "vue", "nuxt", "THREE"]
    c = collections.Counter()
    for d in results.values():
        for k in keys:
            if d.get("stack", {}).get(k):
                c[k] += 1
        a = d.get("assets") or {}
        if a.get("models"): c["ships3D"] += 1
        if a.get("video"): c["video"] += 1
        if d.get("canvasCount"): c["canvas"] += 1
    rec = {"date": datetime.date.today().isoformat(), "n": len(results), **dict(c)}
    if not DRY:
        os.makedirs(STATE, exist_ok=True)
        with open(os.path.join(STATE, "history.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")
    log(f"  trends: {rec}")


def rebuild_trends_md():
    p = os.path.join(STATE, "history.jsonl")
    if not os.path.exists(p):
        return
    recs = [json.loads(l) for l in open(p) if l.strip()]
    if not recs:
        return
    keys = ["gsap", "ScrollTrigger", "Lenis", "barba", "next", "vue",
            "THREE", "ships3D", "video", "canvas"]
    out = ["# Trends — stack share over time", "",
           "Each row is one weekly harvest of *newly seen* SOTD winners. Small n per row;",
           "read the direction across rows, not any single week.", "",
           "| date | n | " + " | ".join(keys) + " |",
           "|---|---|" + "---|" * len(keys)]
    for r in recs[-26:]:
        out.append(f"| {r['date']} | {r['n']} | " +
                   " | ".join(str(r.get(k, 0)) for k in keys) + " |")
    tot = collections.Counter()
    n = 0
    for r in recs:
        n += r["n"]
        for k in keys:
            tot[k] += r.get(k, 0)
    out += ["", f"**Cumulative ({n} sites):** " +
            " · ".join(f"{k} {tot[k]} ({100*tot[k]//max(n,1)}%)" for k in keys)]
    if not DRY:
        open(os.path.join(REFS, "trends.md"), "w").write("\n".join(out) + "\n")
    log(f"  trends.md: {len(recs)} harvests, {n} sites cumulative")


def main():
    log(f"design-radar accumulate — {datetime.datetime.now():%Y-%m-%d %H:%M}")
    os.makedirs(STATE, exist_ok=True)
    os.makedirs(REFS, exist_ok=True)

    log("[1/3] techniques (Codrops)")
    fresh = lane_techniques()
    tech_failed = fresh is None           # distinct from a genuinely quiet week
    append_ideas(fresh)
    fresh = fresh or []

    log("[2/3] evidence (Awwwards)")
    targets, seen = resolve_targets(MAX_RENDER)
    results = render(targets)
    append_trends(results)
    for slug, url in targets.items():
        seen[slug] = {"url": url, "seen": datetime.date.today().isoformat(),
                      "rendered": slug in results}
    save("seen-sites.json", seen)
    rebuild_corpus()   # after save — reads seen-sites.json as its source of truth

    log("[3/3] heartbeat")
    if not DRY:
        with open(os.path.join(STATE, "heartbeat.txt"), "w") as f:
            f.write(f"{datetime.datetime.now().isoformat()}\n"
                    f"new_techniques={'FAILED' if tech_failed else len(fresh)}\n"
                    f"new_sites={len(results)}\n"
                    f"corpus_total={len(seen)}\n")
    rebuild_trends_md()
    log(f"done. +{'FAILED' if tech_failed else len(fresh)} techniques, "
        f"+{len(results)} sites, {len(seen)} sites known total.")
    # A lane can die while every other lane succeeds. Reporting rc=0 here is how
    # the Codrops 410 went unnoticed for a week (2026-09-20: "done. +0 techniques").
    # `launchctl list` shows the last exit code — make it say something.
    if tech_failed:
        log("  !! techniques lane FAILED — exiting 1 so launchctl shows it")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
