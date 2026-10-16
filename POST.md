---
title: I gave Windows a Dynamic Island that writes my timesheet, and my screen never leaves my laptop
published: false
tags: devchallenge, hf26challenge, opensource, ai
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 2: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12)*

<!-- TODO (you): replace this opening with YOUR real moment. Example shape, only if true:
"Last month I invoiced a client for 6 hours. My git log said 9. I'd just... forgotten." -->

If you bill by the hour, your timesheet is a lie. Not on purpose. You forget to start the timer, you switch between three clients before lunch, and on the last Friday of the month you reconstruct your week from browser history and vibes.

The tools that fix this want one of two things: your money, or your screen.

- **Your money:** in 2026, Harvest customers opened renewal bills that had jumped after the Bending Spoons acquisition. One UK consultant's monthly bill reportedly went from **$130 to $2,110** ([Silicon UK](https://www.silicon.co.uk/e-enterprise/merger-acquisition/harvest-price-shock-631249)).
- **Your screen:** automatic trackers work by watching what you do and sending it to their cloud. Your screen is your client's code, your DMs, your bank tab. When Microsoft tried a local version of "watch everything" with Recall, people hated it so much that Signal and Brave shipped features to block it.

So I built **lowkey**: it bills your hours, lowkey. It's a Dynamic Island for Windows that watches what you work on and lets an **open-weight model running on my own GPU** turn it into invoice lines. Nothing about my screen ever leaves my laptop.

## What I Built

**lowkey** has three parts:

**🏝️ The island.** A black pill at the top of the screen, like the iPhone's Dynamic Island:

- It shows the client I'm on, today's billable hours and ₹ earned.
- Hover, and it expands to show what the AI thinks I'm doing right now.
- **go dark** pauses tracking (for when you're doing something nobody needs a log of).
- **not work** marks the current session personal.
- When I switch to another client's work, it pops out: *"switched to Nimbus Labs"*.

<!-- TODO: GIF of the island collapsed → hover → switch toast -->

**🧾 The dashboard** at `localhost:7777`:

- My day as colour blocks, one per client.
- One card per work session, with an AI-written invoice line like *"Developed auth logic, edited login.tsx, fixed OAuth redirect for acme-website."*
- I review cards like a feed: **bill it ✅ / nah 🙅**, or `Y`/`N` with `J`/`K` to move.
- Every card has a **🧾 why?** button that shows the exact windows behind that line. If a client ever asks "what did I pay for?", I have receipts.

**💸 Send the bill.** A receipt-style invoice per client, saved as PDF or copied as CSV.

**✨ Wrapped.** My week as a shareable card: main character client, longest flow state, hours lost to side quests.

<!-- TODO: screenshot of dashboard + wrapped card -->

**Who pays for this?** Freelancers and small agencies who bill hourly. They already pay for time tracking ($9–14 per user per month on Harvest's list prices alone), and the ones under NDA can't paste client work into a cloud AI at all. lowkey is MIT-licensed and free to run. A paid version would be the boring stuff: a one-click installer, a Mac build and invoice templates. <!-- TODO: replace with what your first user said they'd pay -->

## Demo

<!-- TODO: 60–90s video. Suggested shots:
1. The island collapsed, working in VS Code
2. Switch to a different client's repo, the "switched to" pop
3. Hover, expanded view, "go dark"
4. Open the dashboard, Y Y N through cards, "why?" on one card
5. Send the bill, the receipt invoice
6. Wrapped
7. Task Manager / airplane mode showing it still works offline -->

Try the bundled demo week without tracking anything: `python lowkey.py --demo`.

## Code

{% github REPLACE_WITH_YOUR_USERNAME/lowkey %}

## How I Built It

The whole thing is about 700 lines, mostly Python standard library plus one HTML file. No Electron, no framework, no cloud account.

**1. The tracker (stdlib `ctypes`, no dependencies).**
- Every 5 seconds it reads the foreground window title and process name, and how long since the last keypress.
- If I've been idle for more than 5 minutes, if I hit **go dark**, or if the window matches a `never_track` entry (password managers, private browsing), nothing is written.
- Everything else goes to a JSONL file on disk that I can open and read.

**2. The labeller: Gemma 4 E2B on Ollama.**
- Every 15-minute slot of activity goes to `gemma4:e2b`, running on my RTX 4050 laptop GPU (6 GB VRAM).
- It gets my client list plus "hints" (repo names, domains) and returns `{client, task, billable}`.
- The output is constrained by a JSON schema, and the client field is an enum of my real clients. The model literally cannot invent a client.

**3. The second pass.**
- Consecutive slots for the same client merge into one session.
- Gemma then rewrites that session's notes into one invoice line, past tense, specific (files, PR numbers), max 90 characters.

**4. The honesty number: "backed by your windows".**
- The model's self-reported confidence was useless: it said 100% on everything.
- So the confidence on each card is computed by plain code instead: the share of that session's time whose window titles actually match the chosen client.
- Low share means the card says *"🤔 check me"*. The model writes the line; code decides how much to trust it.

**5. The UI.**
- Neo-brutalist, deliberately loud: thick outlines, hard shadows, client colours.
- It uses Windows' own Bahnschrift font, so the page makes **zero** external requests. No Google Fonts, no CDN.
- The island is tkinter with a transparent key colour, drawn with real circles, so it's a proper pill and not a rounded rectangle.

### What went wrong (and what I changed)

- **Gemma 4 thinks out loud by default.** My first labelling call took **9.5 s** because the model produced a whole "Thinking Process" before answering. With thinking off and a JSON schema, the same call takes **~0.3 s**. For 15-minute slots, 30× faster is the difference between "live" and "eventually".
- **"100% sure" on every card.** See the honesty number above. A judge model grading itself is not a metric.
- **Repetitive invoice lines.** Merging slots first gave me lines like *"Modified product card code for theme; Modified product card for chaico theme; …"*. The second Gemma pass fixed it: *"Modified product card code/theme, previewed Masala Chai 250g, reviewed liquid file, accessed Shopify orders."*

### Numbers

| Test | Gemma 4 E2B (local) | Keyword rules |
|---|---|---|
| Right client per 15-min slot, synthetic demo week (155 slots) | 152 / 155 (98.1%) | 150 / 155 (96.8%) |
| Right client per slot, **my real day** | <!-- TODO --> | <!-- TODO --> |
| Invoice line usable without edits, real day | <!-- TODO: n/N --> | n/a (rules can't write) |
| Label latency, RTX 4050 6 GB | ~0.3–0.6 s | instant |

The synthetic week is easy for keywords on purpose, since its window titles contain client names. All 3 of Gemma's misses there were slots split almost 50/50 between work and personal. The real-day rows are the ones that matter. <!-- TODO: fill after labelling one real day by hand -->

## Why Does Open Innovation Matter?

For this project it isn't a nice-to-have. lowkey couldn't exist on a closed API.

1. **The data is the most private thing on my computer.** Window titles are client names, repo names, DM previews and the name of the doctor I booked. Sending that to a cloud model every 15 minutes, all day, is not a privacy policy question; it's a hard no. An open-weight model on my GPU means the data has nowhere to go. You don't have to trust my privacy policy: the code is open and the server binds to `127.0.0.1`.
2. **Always-on is expensive, unless it's free.** A tracker labels ~30–40 slots a day, every day, forever. On my own GPU that costs nothing per label. Pay-per-token pricing is exactly how a time tracker turns into a $2,110 bill.
3. **I can see and constrain the model.** With Ollama I can force a JSON schema, pin the client to an enum, turn off "thinking" when it wastes 9 seconds, and swap Gemma for Qwen with one environment variable.
4. **Nobody can reprice it on me.** No acquisition can turn this into a usage-based bill. The weights are on my disk.

## My Agent Session

<!-- TODO: embed the DevRelay session (judges like it). Remove anything private first. -->

## My First User

<!-- TODO: ONLY write what really happened. Who (a freelancer you know), how long they ran it,
how many hours it caught that they would have forgotten, what it got wrong, whether they'd pay (ask a concrete price,
e.g. "₹299 once?"), and what they asked for next. If nobody tried it, delete this section; don't invent one. -->

## Prize Categories

- **Best Use of Gemma**: Gemma 4 E2B does all the labelling and the invoice-line writing, locally via Ollama, with a JSON schema and thinking turned off.
