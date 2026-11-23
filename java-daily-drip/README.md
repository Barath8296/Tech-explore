# ☕ Java Daily Drip → WhatsApp (₹0 forever)

One beginner-friendly Java backend lesson on your WhatsApp every morning (~7:53 AM IST).
Everything in it is free:

| Part | Service | Cost |
|---|---|---|
| Find what's new | Free RSS feeds (`feeds.txt`): Spring blog, Inside Java, InfoQ, Baeldung, Netflix/Meta/AWS engineering blogs, Hacker News | ₹0 |
| Explain it | **Groq** free tier (no card; at the limit it just stops, it never bills) | ₹0 |
| Run daily | GitHub Actions in a private repo (uses ~2 min/day of the free monthly minutes) | ₹0 |
| Deliver | **Green-API** free Developer plan, CallMeBot or Telegram | ₹0 |

## Two kinds of lessons
- 🌐 **News:** reads the feeds, keeps articles from the last 14 days, lets the AI pick the most beginner-friendly one and explains it with the link.
- 📘 **Classic:** the next fundamental from `topics.txt`.

The default `mix` mode sends **2 news days, then 1 classic day**, repeating.

**It never misses a day.** If a feed is down, it's skipped. If there's no fresh news, you get a classic lesson. If the AI is unavailable, you still get the headline, summary and link, or the day's topic. Links and topics are remembered in `progress.json`, so nothing repeats.

## 🚫 No repeats, ever
Each new topic is checked against **everything ever sent**, not just exact matches. `dedupe.py` is free and needs no AI.
- **Same link:** blocked.
- **Reworded:** blocked. For example, "What's new in Spring Boot 4" vs "Spring Boot 4 released", or "Virtual Threads in Java explained" vs "Java 25 virtual threads deep dive".
- **Same core concept:** blocked. The AI tags each lesson and puzzle with a short concept, such as "virtual threads" or "Integer caching", and that's checked too.
- **Across types:** a news day about something in your topic list means that basics topic is skipped later.

If the AI suggests a repeat, it's rejected and asked again: 3 tries for news, 5 for puzzles. If a puzzle can't be made new, that day is **skipped** rather than repeated. Want a topic again on purpose? Remove it from `progress.json` or `puzzle_state.json`.
Run `python dedupe.py` to self-test the checker.

## 🧩 Bonus: Daily Coding Puzzle (same repo, same keys)
- **8:37 AM:** a puzzle with a hint. **8:37 PM:** the answer, a short Java/SQL solution, time/space complexity and a common mistake.
- **10 rotating types:** Predict the output · Arrays & Strings · HashMap thinking · Find the bug · Two pointers · Stack & Queue · SQL · Recursion · Streams API · Backend design mini.
- **Difficulty ramps slowly:** Easy → Easy+ → Medium-, rising about every 30 days.
- **AI is only used in the morning.** The evening answer is saved, so it always arrives. If the AI is down, a built-in classic puzzle is used.
- **Test it:** Actions → **Daily Coding Puzzle** → Run workflow → choose `morning`, then run again with `evening`.
- **Turn it off:** Actions → Daily Coding Puzzle → ⋯ → **Disable workflow**.

## Setup (about 15 minutes)

### 1. WhatsApp sender: pick ONE option

**Option A: Green-API (recommended, free Developer plan)**
1. Sign up at https://green-api.com and open the console.
2. **Create instance**, then choose the free **Developer** plan.
3. Scan the QR code from WhatsApp → **Settings → Linked devices → Link a device**.
   - 👍 **Best:** link a **second/spare WhatsApp number** as the sender, so the lessons arrive on your main number *with notifications*.
   - Only one number? Link it anyway. Messages will appear in your **"You" (message yourself)** chat, but WhatsApp won't send a notification for them.
4. From the instance page, copy **idInstance**, **apiTokenInstance** and **apiUrl**.

> Green-API is an unofficial gateway, so there's a small ban risk. At 3 messages a day it's very low, but a spare number is safest.

**Option B: CallMeBot.** Use this only if their page shows a phone number. If it says "bot is currently full", use A.
Save the bot number from https://www.callmebot.com/blog/free-api-whatsapp-messages/, send it `I allow callmebot to send me messages`, and note the apikey it replies with.

**Option C: Telegram (no WhatsApp, 100% reliable).** In Telegram, message **@BotFather** → `/newbot` → copy the token. Send your new bot "hi", then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `"chat":{"id": ...}`.

### 2. Groq key (AI)
Sign up at https://console.groq.com, go to **API Keys**, then **Create**. **Don't add a payment method**, so it stays on the free plan.

### 3. GitHub
1. Create a **private** repo and upload all files, including the `.github/workflows` folder.
2. Go to **Settings → Secrets and variables → Actions → New repository secret**. Add `GROQ_API_KEY`, plus the secrets for the sender you chose:
   | Option | Secrets to add |
   |---|---|
   | **A: Green-API** | `GREENAPI_ID` = idInstance · `GREENAPI_TOKEN` = apiTokenInstance · `GREENAPI_URL` = apiUrl · `WHATSAPP_PHONE` = number to receive on (`+91...`) |
   | B: CallMeBot | `CALLMEBOT_APIKEY` · `WHATSAPP_PHONE` |
   | C: Telegram | `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` |

   The code picks the sender automatically from whichever secrets exist. If several are set, Green-API is used first.

### 4. Test
Go to **Actions → Java Daily Drip → Run workflow**. Day 1 should arrive on WhatsApp within a minute or two. The log shows which feeds worked.

## Customise
- **Feeds:** edit `feeds.txt` and add any RSS/Atom URL, such as your favourite blogs or a Medium tag (`https://medium.com/feed/tag/spring-boot`).
- **Mode:** add the repo **Variable** `DRIP_MODE` = `mix`, `news` or `classic`.
- **Model:** Groq renames models sometimes. If the log shows a "model not found" error, pick a current model at console.groq.com/docs/models and set the repo **Variable** `LLM_MODEL`.
- **Style:** edit `NEWS_PROMPT` and `CLASSIC_PROMPT` in `drip.py`. You can ask for Tamil explanations, interview questions or more code.
- **Time:** change `cron` in the workflow. It's in UTC; IST = UTC + 5:30.
- **Restart from Day 1:** set `progress.json` to `{"day": 0, "covered": [], "sources": []}`.

## Run locally (optional)
```bash
export GROQ_API_KEY=...  WHATSAPP_PHONE=+91...  CALLMEBOT_APIKEY=...
python drip.py --dry-run --news   # preview a news lesson, nothing sent
python drip.py                    # send for real
```

## Notes
- GitHub pauses schedules in repos with 60 days of no activity. The daily progress commit keeps this repo active.
- Green-API/CallMeBot and Groq are third-party free services, and your lesson text passes through them. That's fine for learning content, but don't send anything private this way.
