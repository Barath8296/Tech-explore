#!/usr/bin/env python3
"""
Daily Coding Puzzle -> WhatsApp   (₹0: Groq free tier + CallMeBot + GitHub Actions)

  python puzzle.py --morning   generate today's puzzle, send the QUESTION, save the answer
  python puzzle.py --evening   send the saved ANSWER (no AI call needed)

Puzzle types rotate daily, and difficulty grows slowly with the day number.
If the AI is down in the morning, a built-in puzzle is used, so you never miss a day.

Reuses the AI and WhatsApp helpers from drip.py (same env vars).
Flags: --dry-run (print only; nothing sent or saved)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from dedupe import is_repeat
from drip import IST, MAX_CHARS, ask_llm, send_whatsapp

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "puzzle_state.json"

CATEGORIES = [
    ("🔮 Predict the output", "a short tricky Java snippet (max 10 lines); ask what it prints. "
     "Use real Java gotchas: Integer caching, String immutability, ==, i++ vs ++i, "
     "integer overflow, switch fall-through, char arithmetic, static vs instance, etc."),
    ("🧮 Arrays & Strings", "a small LeetCode-easy style problem on arrays or strings"),
    ("🗂️ HashMap thinking", "a problem best solved with a HashMap/HashSet (counting, duplicates, lookups)"),
    ("🐞 Find the bug", "a short Java/Spring snippet (max 12 lines) with ONE realistic backend bug "
     "(null handling, equals/hashCode, resource leak, wrong transaction, off-by-one, thread-safety)"),
    ("👉 Two pointers / Sliding window", "a beginner-friendly two-pointer or sliding-window problem"),
    ("🧱 Stack & Queue", "a problem naturally solved with a stack or queue"),
    ("🗄️ SQL challenge", "a small SQL query problem on 1-2 tiny tables (show the tables as text)"),
    ("🔁 Recursion", "a gentle recursion problem"),
    ("⚙️ Streams API", "a Java Streams transformation problem on a small list of records"),
    ("🏗️ Backend design mini", "a tiny design question (e.g. design a URL shortener's ID generator, "
     "rate limiter idea, cache key choice) answerable in a few lines"),
]

LEVELS = ["Easy", "Easy", "Easy+", "Medium-", "Medium"]

PROMPT = """You create a daily coding puzzle for a beginner-to-intermediate Java backend developer,
delivered on WhatsApp. Today: Day {day}, category "{cat}" — {desc}. Difficulty: {level}.
Do NOT repeat any previous puzzle, even reworded or with different numbers. Already used (title | concept):
{previous}

Reply with ONLY a JSON object (no markdown fences) with these keys:
"title": short catchy title (max 8 words)
"concept": the core idea being tested in 2-5 words (e.g. "Integer caching", "two sum hashmap")
"question": the puzzle text for WhatsApp: problem statement, an example (input -> output) if relevant,
  constraints in one line. Code goes inside ```triple backticks```. Max 700 characters.
"hint": one-line hint that does not give the answer away
"answer": the solution for WhatsApp: 1) the answer/approach in 2-3 lines, 2) a short Java (or SQL)
  solution inside ```triple backticks``` max 15 lines, 3) "⏱️ Time/Space: ..." 4) "⚠️ Common mistake: ..."
  Max 1000 characters.
Use WhatsApp formatting only (*bold*, _italic_, ```code```). Double-check the answer is correct."""

FALLBACK = [
    {"title": "Integer cache surprise",
     "question": "What does this print?\n```Integer a = 127, b = 127;\nInteger c = 128, d = 128;\n"
                 "System.out.println(a == b);\nSystem.out.println(c == d);```",
     "hint": "Java caches some Integer objects.",
     "answer": "*true* then *false*.\nJava caches Integer objects from -128 to 127, so a and b are the same "
               "object. 128 creates two different objects, and == compares references.\n"
               "```System.out.println(c.equals(d)); // true```\n⏱️ Time/Space: O(1)\n"
               "⚠️ Common mistake: using == on wrapper types. Always use equals()."},
    {"title": "First non-repeating character",
     "question": "Given a string, return the first character that appears only once, or '_' if none.\n"
                 "Example: \"swiss\" -> 'w'",
     "hint": "Count first, then scan again.",
     "answer": "Count each char with a LinkedHashMap (or an int[256]), then scan in order.\n"
               "```static char first(String s){\n  int[] c = new int[256];\n  for (char ch : s.toCharArray()) c[ch]++;\n"
               "  for (char ch : s.toCharArray()) if (c[ch]==1) return ch;\n  return '_';\n}```\n"
               "⏱️ Time/Space: O(n) / O(1)\n⚠️ Common mistake: nested loops, which are O(n²)."},
    {"title": "Spot the missing equals",
     "question": "Why does this print *false*?\n```class User { String id; User(String i){id=i;} }\n"
                 "Set<User> s = new HashSet<>();\ns.add(new User(\"1\"));\n"
                 "System.out.println(s.contains(new User(\"1\")));```",
     "hint": "How does HashSet decide two objects are the same?",
     "answer": "User doesn't override *equals()* and *hashCode()*, so HashSet compares memory addresses.\n"
               "```@Override public boolean equals(Object o){\n  return o instanceof User u && id.equals(u.id);\n}\n"
               "@Override public int hashCode(){ return id.hashCode(); }```\n"
               "Or simply: `record User(String id) {}`\n⏱️ Time/Space: O(1) lookup\n"
               "⚠️ Common mistake: overriding equals but not hashCode."},
    {"title": "Two Sum with a HashMap",
     "question": "Given int[] nums and target, return indexes of two numbers that add up to target.\n"
                 "Example: [2,7,11,15], 9 -> [0,1]",
     "hint": "For each number, ask: have I already seen target - num?",
     "answer": "Store each number's index in a HashMap and look up the complement.\n"
               "```Map<Integer,Integer> m = new HashMap<>();\nfor (int i = 0; i < nums.length; i++) {\n"
               "  Integer j = m.get(target - nums[i]);\n  if (j != null) return new int[]{j, i};\n"
               "  m.put(nums[i], i);\n}\nreturn new int[0];```\n⏱️ Time/Space: O(n) / O(n)\n"
               "⚠️ Common mistake: putting into the map before checking, which can match an element with itself."},
    {"title": "Count orders per customer",
     "question": "Table *orders(id, customer_id, amount)*. Write SQL to list each customer_id with "
                 "their order count and total amount, only for customers with more than 2 orders.",
     "hint": "GROUP BY, then filter groups.",
     "answer": "Group by customer and filter with HAVING (WHERE can't filter aggregates).\n"
               "```SELECT customer_id, COUNT(*) AS orders, SUM(amount) AS total\nFROM orders\n"
               "GROUP BY customer_id\nHAVING COUNT(*) > 2;```\n⏱️ Time/Space: one scan of the table\n"
               "⚠️ Common mistake: writing WHERE COUNT(*) > 2."},
]


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"day": 0, "titles": [], "concepts": [], "pending": None}


def save_state(state):
    state["titles"] = state["titles"][-2000:]
    state["concepts"] = state.get("concepts", [])[-2000:]
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_json(raw):
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip())
    start, end = raw.find("{"), raw.rfind("}")
    data = json.loads(raw[start:end + 1])
    for k in ("title", "question", "hint", "answer"):
        if not str(data.get(k, "")).strip():
            raise ValueError(f"missing {k}")
    return data


def fit(text):
    if len(text) <= MAX_CHARS:
        return text
    cut = text[: MAX_CHARS - 3]
    if cut.count("```") % 2 == 1:
        cut = cut[: MAX_CHARS - 8] + "\n```"
    return cut + "\n…"


def pick_puzzle(state, day):
    """AI puzzle that isn't a repeat (3 tries), else an unused built-in one, else None."""
    state.setdefault("concepts", [])
    past = state["titles"] + state["concepts"]
    cat, desc = CATEGORIES[(day - 1) % len(CATEGORIES)]
    level = LEVELS[min((day - 1) // 30, len(LEVELS) - 1)]  # harder every ~30 days
    used = [f"{t} | {c}" for t, c in zip(state["titles"][-80:], state["concepts"][-80:])] or ["(none)"]
    blocked = []
    for attempt in range(5):
        try:
            p = parse_json(ask_llm(PROMPT.format(day=day, cat=cat, desc=desc, level=level,
                                                 previous="\n".join(f"- {u}" for u in used + blocked))))
        except Exception as e:
            print(f"AI unavailable ({e}).", file=sys.stderr)
            break
        dup = is_repeat([p["title"], p.get("concept", "")], past)
        if not dup:
            return p, cat, level
        print(f"  repeat blocked: '{p['title']}' ~ '{dup}' (attempt {attempt + 1})", file=sys.stderr)
        blocked.append(f"{p['title']} | {p.get('concept', '')}")
    for f in FALLBACK:  # built-in puzzles, each used at most once ever
        if not is_repeat([f["title"]], past):
            print("Using a built-in puzzle.", file=sys.stderr)
            return f, "🧩 Classic puzzle", "Easy"
    return None, cat, level


def morning(state, dry_run):
    day = state["day"] + 1
    p, cat, level = pick_puzzle(state, day)
    if p is None:  # never repeat: skip today rather than resend an old puzzle
        print("No new puzzle available today (AI down and built-ins used up). Skipping, nothing sent.")
        return

    msg = fit(f"🧩 *Puzzle #{day}: {p['title']}*\n_{cat} · {level}_\n\n{p['question'].strip()}\n\n"
              f"💭 *Hint:* {p['hint'].strip()}\n\n_Answer arrives at 8:37 PM. Try it before then!_ ⏳")
    print(msg, f"\n({len(msg)} chars)")
    if dry_run:
        print("\n[evening preview]\n" + evening_text(day, p))
        return
    send_whatsapp(msg)
    state["day"] = day
    state["titles"].append(p["title"])
    state["concepts"].append(p.get("concept") or p["title"])
    state["pending"] = {"day": day, "title": p["title"], "answer": p["answer"]}
    save_state(state)


def evening_text(day, p):
    return fit(f"✅ *Puzzle #{day} answer: {p['title']}*\n\n{p['answer'].strip()}\n\n"
               f"_Did you get it? New puzzle tomorrow at 8:37 AM._ 💪")


def evening(state, dry_run):
    pend = state.get("pending")
    if not pend:
        print("No pending puzzle; nothing to send.")
        return
    msg = evening_text(pend["day"], pend)
    print(msg, f"\n({len(msg)} chars)")
    if dry_run:
        return
    send_whatsapp(msg)
    state["pending"] = None
    save_state(state)


def main():
    dry_run = "--dry-run" in sys.argv
    state = load_state()
    if "--evening" in sys.argv:
        evening(state, dry_run)
    elif "--morning" in sys.argv:
        morning(state, dry_run)
    else:
        sys.exit("Use --morning or --evening")
    print("Done ✅", datetime.now(IST).strftime("%d %b %Y %H:%M IST"))


if __name__ == "__main__":
    main()
