#!/usr/bin/env python3
"""
Java Backend Daily Drip -> WhatsApp   (100% free stack)

  Find:     free RSS/Atom feeds (feeds.txt): Spring blog, InfoQ, Inside Java,
            engineering blogs, Hacker News...
  Explain:  Groq free-tier LLM (no card needed; on limit it just says "429", never bills)
  Deliver:  CallMeBot free WhatsApp API (personal use)
  Run:      GitHub Actions free cron

Two kinds of daily lessons:
  🌐 NEWS    picks the most beginner-interesting fresh article from the feeds and explains it,
             with the link
  📘 CLASSIC the next fundamental from topics.txt

DRIP_MODE: mix (default: 2 news days, then 1 classic) | news | classic

If the AI is unavailable, it still sends something useful without AI (headline, summary
and link, or today's topic), so you never miss a day. Sent links and topics are saved in
progress.json, so nothing repeats.

Needs only the Python standard library.

Environment variables:
  GROQ_API_KEY        free key from console.groq.com
  WHATSAPP_PHONE      your number with country code, e.g. +919876543210
  CALLMEBOT_APIKEY    the key CallMeBot sent you on WhatsApp
  LLM_MODEL           optional, default openai/gpt-oss-120b (any Groq model works)
  LLM_BASE_URL        optional, default https://api.groq.com/openai/v1
                      (any OpenAI-compatible endpoint works, e.g. Gemini's free tier)
  DRIP_MODE           optional: mix | news | classic

Flags:
  --dry-run            print the message only, don't send or save progress
  --news / --classic   force today's lesson type
"""

import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from dedupe import is_repeat

HERE = Path(__file__).resolve().parent
TOPICS_FILE = HERE / "topics.txt"
FEEDS_FILE = HERE / "feeds.txt"
PROGRESS_FILE = HERE / "progress.json"
IST = timezone(timedelta(hours=5, minutes=30))

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")
MODE = os.environ.get("DRIP_MODE", "mix").strip().lower()
MAX_CHARS = 1500          # short WhatsApp message, safe GET URL
FRESH_DAYS = 14           # only consider articles from the last N days
MAX_CANDIDATES = 25       # how many fresh articles the AI chooses from
UA = "Mozilla/5.0 (JavaDailyDrip; personal learning bot)"

FORMAT_RULES = f"""Formatting rules (WhatsApp):
- Max {MAX_CHARS} characters total. Beginner-friendly: explain any jargon in a few words.
- WhatsApp formatting only: *bold*, _italic_, ```code```. No markdown headings, tables or [text](url) links.
- Interesting and fresh, not a textbook definition. Don't invent facts beyond the article info given."""

NEWS_PROMPT = """You are a friendly senior Java backend engineer who sends a beginner one exciting
"what's new in backend" lesson on WhatsApp every day.

Here are fresh articles from Java/backend news feeds (number. [source] title / summary / link):

{candidates}

Step 1: Pick the ONE article that is most interesting AND understandable for a beginner Java backend
developer. Prefer new releases, new tools, real-world engineering stories and practical techniques.
Avoid pure marketing, job posts, and ANY topic or concept already covered (even if worded differently):
{covered}

Step 2: Reply in EXACTLY this format and nothing else:
PICK: <article number>
TOPIC: <short title, max 10 words>
CONCEPT: <the core concept in 2-4 words, e.g. "virtual threads" or "database indexing">
MESSAGE:
🌐 *Day {day}: <catchy title>*
<What's new, in 1-2 lines>
<Why it matters / real-life analogy, 2-3 short lines>
<Tiny Java/Spring code example (max ~8 lines) ONLY if it genuinely helps>
💡 *Beginner takeaway:* <one line connecting it to a fundamental concept>
🧠 *Try this:* <one small 5-minute action>

{format_rules}"""

CLASSIC_PROMPT = """You are a friendly senior Java backend engineer mentoring a beginner over WhatsApp.

Today's topic (Day {day}): {topic}

Write ONE short lesson message with this structure:
1. First line: "📘 *Day {day}: <short catchy title>*"
2. A real-life analogy or "why should I care" hook (1-2 lines)
3. The core idea in 2-4 short lines
4. A tiny Java/Spring code example (max ~8 lines) if it fits the topic
5. "💡 *Pro tip:*" one surprising or practical line
6. "🧠 *Try this:*" one small question or 5-minute exercise

{format_rules}
Output only the message text."""

NEW_TOPIC_PROMPT = """Suggest ONE new beginner-friendly Java backend fundamentals topic (Java, Spring Boot,
databases, APIs, testing, security, DevOps basics, system design basics) that is NOT in this list:

{covered}

Reply with the topic title only, one line, no quotes."""


# ---------- helpers ----------

def load_progress():
    p = {"day": 0, "covered": [], "sources": [], "concepts": [], "article_titles": []}
    if PROGRESS_FILE.exists():
        p.update(json.loads(PROGRESS_FILE.read_text(encoding="utf-8")))
    return p


def save_progress(progress):
    for k in ("covered", "sources", "concepts", "article_titles"):
        progress[k] = progress[k][-2000:]
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_list(path):
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]


def bullet_list(items, limit, empty="(none yet)"):
    items = items[-limit:]
    return "\n".join(f"- {i}" for i in items) if items else empty


def history(progress):
    """Everything ever sent: titles, core concepts and article headlines."""
    return [t.lstrip("🌐 ").strip() for t in progress["covered"]] + progress["concepts"] + progress["article_titles"]


def clean_text(s, limit=300):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] + ("…" if len(s) > limit else "")


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ---------- feeds ----------

def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child(el, *names):
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def _parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)  # RSS style
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))  # Atom style
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_feed(raw, feed_url):
    root = ET.fromstring(raw)
    source = urllib.parse.urlparse(feed_url).netloc.replace("www.", "")
    items = []
    for el in root.iter():
        kind = _local(el.tag)
        if kind not in ("item", "entry"):
            continue
        title = clean_text((_child(el, "title").text if _child(el, "title") is not None else ""), 160)
        link_el = _child(el, "link")
        link = ""
        if link_el is not None:
            link = (link_el.get("href") or link_el.text or "").strip()
        summary_el = _child(el, "description", "summary", "content", "encoded")
        summary = clean_text(summary_el.text if summary_el is not None else "")
        date_el = _child(el, "pubdate", "published", "updated", "date")
        date = _parse_date(date_el.text if date_el is not None else None)
        if title and link.startswith("http"):
            items.append({"title": title, "link": link, "summary": summary, "date": date, "source": source})
    return items


def fresh_articles(progress):
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESH_DAYS)
    seen = set(progress["sources"])
    past = history(progress)
    articles = []
    for url in read_list(FEEDS_FILE):
        try:
            got = parse_feed(http_get(url), url)
            print(f"  feed ok  ({len(got):>3} items) {url}")
            articles += got
        except Exception as e:
            print(f"  feed skip ({type(e).__name__}) {url}", file=sys.stderr)
    uniq, links = [], set()
    for a in articles:
        if a["link"] in seen or a["link"] in links:
            continue
        if a["date"] and a["date"] < cutoff:
            continue
        if is_repeat([a["title"]], past):  # same story/topic already sent
            continue
        links.add(a["link"])
        uniq.append(a)
    uniq.sort(key=lambda a: a["date"] or cutoff, reverse=True)
    # keep variety: max 5 per source
    per, picked = {}, []
    for a in uniq:
        if per.get(a["source"], 0) < 5:
            per[a["source"]] = per.get(a["source"], 0) + 1
            picked.append(a)
    return picked[:MAX_CANDIDATES]


# ---------- LLM (OpenAI-compatible: Groq by default) ----------

def ask_llm(prompt, max_tokens=2500):
    key = os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY")
    if not key:
        raise RuntimeError("No GROQ_API_KEY set")
    body = {"model": LLM_MODEL, "max_tokens": max_tokens, "temperature": 0.7,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        LLM_BASE_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = (data["choices"][0]["message"].get("content") or "").strip()
            if text:
                return text
            raise RuntimeError("empty reply")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:  # free-tier limit hit: wait and retry
                time.sleep(30 * (attempt + 1))
                continue
            raise RuntimeError(f"LLM error {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    raise RuntimeError("LLM failed")


# ---------- lessons ----------

def news_lesson(progress, day):
    """Returns a lesson dict. Retries if the AI picks something already covered.
    Without AI it still returns a headline digest of a not-yet-sent article."""
    articles = fresh_articles(progress)  # already excludes sent links and similar headlines
    if not articles:
        raise RuntimeError("no fresh, not-yet-covered articles in feeds")
    past = history(progress)
    rejected = []
    try:
        for attempt in range(3):
            pool = [a for a in articles if a["link"] not in rejected]
            if not pool:
                break
            candidates = "\n".join(
                f"{i}. [{a['source']}] {a['title']}\n   {a['summary']}\n   {a['link']}"
                for i, a in enumerate(pool, 1))
            raw = ask_llm(NEWS_PROMPT.format(candidates=candidates, covered=bullet_list(past, 80),
                                             day=day, format_rules=FORMAT_RULES))
            art = pool[int(re.search(r"PICK:\s*(\d+)", raw).group(1)) - 1]
            topic = re.search(r"TOPIC:\s*(.+)", raw).group(1).strip()
            m = re.search(r"CONCEPT:\s*(.+)", raw)
            concept = m.group(1).strip().strip('"') if m else ""
            dup = is_repeat([topic, concept, art["title"]], past)
            if dup:
                print(f"  repeat blocked: '{topic}' ~ '{dup}' (attempt {attempt + 1})", file=sys.stderr)
                rejected.append(art["link"])
                continue
            body = raw.split("MESSAGE:", 1)[1].strip()
            if not body.startswith("🌐"):
                body = body[body.find("🌐"):] if "🌐" in body else f"🌐 *Day {day}: {topic}*\n{body}"
            return {"topic": "🌐 " + topic, "concept": concept, "link": art["link"],
                    "article_title": art["title"], "body": body}
        raise RuntimeError("AI kept picking covered topics")
    except Exception as e:  # AI down -> plain but useful digest of a fresh, unsent article
        print(f"AI unavailable for news ({e}); sending headline only.", file=sys.stderr)
        a = next((a for a in articles if a["link"] not in rejected), None)
        if a is None:
            raise RuntimeError("no unsent article left")
        body = f"🌐 *Day {day}: Fresh from {a['source']}*\n*{a['title']}*\n\n{a['summary']}"
        return {"topic": "🌐 " + a["title"], "concept": "", "link": a["link"],
                "article_title": a["title"], "body": body}


def classic_lesson(progress, day):
    past = history(progress)
    # next list topic that hasn't been covered, even under another name (e.g. by a news day)
    topic = next((t for t in read_list(TOPICS_FILE) if not is_repeat([t], past)), None)
    try:
        if topic is None:  # list finished -> AI invents a new fundamental, checked for repeats
            tried = []
            for _ in range(4):
                cand = ask_llm(NEW_TOPIC_PROMPT.format(covered=bullet_list(past + tried, 150)), 400)
                cand = cand.strip().splitlines()[0].strip().strip('"')
                if cand and not is_repeat([cand], past):
                    topic = cand
                    break
                tried.append(cand)
            if topic is None:
                raise RuntimeError("could not find a new topic")
        body = ask_llm(CLASSIC_PROMPT.format(day=day, topic=topic, format_rules=FORMAT_RULES))
    except Exception as e:
        if topic is None:
            raise RuntimeError(f"no new classic topic available ({e})")
        print(f"AI unavailable for classic ({e}); sending topic only.", file=sys.stderr)
        body = (f"📘 *Day {day}: {topic}*\n\nToday's self-study topic. Spend 15 minutes on it: "
                f"read about it, then write a tiny Java example.\n🧠 *Try this:* explain it to yourself in 3 lines.")
    return {"topic": topic, "concept": "", "link": "", "article_title": "", "body": body}


def lesson_type_for(day):
    if "--news" in sys.argv:
        return "news"
    if "--classic" in sys.argv:
        return "classic"
    if MODE in ("news", "classic"):
        return MODE
    return "classic" if day % 3 == 0 else "news"  # mix: news, news, classic...


def finalize(body, link, day_line):
    if body.count("```") % 2 == 1:  # close a code block left open
        body = body.rstrip() + "\n```"
    footer = (f"\n🔗 {link}" if link else "") + f"\n\n_{day_line} · Java Daily Drip_"
    room = MAX_CHARS - len(footer)
    if len(body) > room:
        cut = body[: room - 2]
        cut = cut[: cut.rfind("\n")] if "\n" in cut else cut
        if cut.count("```") % 2 == 1:
            cut += "\n```"
        body = cut + "\n…"
    return body + footer


# ---------- Delivery: Green-API / CallMeBot / Telegram (auto-selected) ----------

def _env(name):
    return (os.environ.get(name) or "").strip()


def delivery_provider():
    """Picks the channel from whichever secrets are set."""
    if _env("GREENAPI_ID") and _env("GREENAPI_TOKEN"):
        return "greenapi"
    if _env("CALLMEBOT_APIKEY"):
        return "callmebot"
    if _env("TELEGRAM_BOT_TOKEN") and _env("TELEGRAM_CHAT_ID"):
        return "telegram"
    raise RuntimeError("No delivery secrets set: add GREENAPI_ID + GREENAPI_TOKEN, "
                       "or CALLMEBOT_APIKEY, or TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID")


def _post_json(url, payload, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _send_once(provider, text):
    if provider == "greenapi":
        base = (_env("GREENAPI_URL") or "https://api.green-api.com").rstrip("/")
        phone = re.sub(r"\D", "", _env("WHATSAPP_PHONE"))  # +91 98765-43210 -> 919876543210
        url = f"{base}/waInstance{_env('GREENAPI_ID')}/sendMessage/{_env('GREENAPI_TOKEN')}"
        body = _post_json(url, {"chatId": f"{phone}@c.us", "message": text})
        if "idMessage" not in body:
            raise RuntimeError(body[:300])
    elif provider == "callmebot":
        url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
            {"phone": _env("WHATSAPP_PHONE"), "text": text, "apikey": _env("CALLMEBOT_APIKEY")})
        body = http_get(url, timeout=60).decode("utf-8", errors="replace")
        if "error" in body.lower():
            raise RuntimeError(body[:300])
    else:  # telegram (WhatsApp *bold* shows as plain asterisks there, still readable)
        url = f"https://api.telegram.org/bot{_env('TELEGRAM_BOT_TOKEN')}/sendMessage"
        body = _post_json(url, {"chat_id": _env("TELEGRAM_CHAT_ID"), "text": text,
                                "disable_web_page_preview": False})
        if '"ok":true' not in body.replace(" ", ""):
            raise RuntimeError(body[:300])


def send_whatsapp(text, retries=3):
    provider = delivery_provider()
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            _send_once(provider, text)
            print(f"Delivered via {provider}")
            return
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception as e:
            last_err = str(e)
        # never print secrets: only the error text
        print(f"Send attempt {attempt} via {provider} failed: {last_err}", file=sys.stderr)
        time.sleep(15 * attempt)
    raise RuntimeError(f"Send failed via {provider}: {last_err}")


# ---------- main ----------

def main():
    dry_run = "--dry-run" in sys.argv
    progress = load_progress()
    day = progress["day"] + 1
    kind = lesson_type_for(day)

    if kind == "news":
        try:
            lesson = news_lesson(progress, day)
        except Exception as e:
            print(f"News failed ({e}); falling back to classic.", file=sys.stderr)
            kind, lesson = "classic", classic_lesson(progress, day)
    else:
        try:
            lesson = classic_lesson(progress, day)
        except Exception as e:
            print(f"Classic failed ({e}); trying news instead.", file=sys.stderr)
            kind, lesson = "news", news_lesson(progress, day)

    message = finalize(lesson["body"], lesson["link"], datetime.now(IST).strftime("%a, %d %b %Y"))
    print(f"Day {day} [{kind}] topic: {lesson['topic']}  | concept: {lesson['concept'] or '-'}")
    print("-" * 40 + "\n" + message + "\n" + "-" * 40)
    print(f"{len(message)} characters")

    if dry_run:
        print("Dry run: not sending, progress not saved.")
        return

    send_whatsapp(message)
    progress["day"] = day
    progress["covered"].append(lesson["topic"])
    for key, field in (("sources", "link"), ("concepts", "concept"), ("article_titles", "article_title")):
        if lesson[field]:
            progress[key].append(lesson[field])
    save_progress(progress)
    print("Sent ✅")


if __name__ == "__main__":
    main()
