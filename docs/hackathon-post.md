---
title: "lowkey: Gemma reads my window titles every 5 minutes and writes my timesheet, without them leaving my laptop"
published: false
tags: devchallenge, hf26challenge, gemma, opensource
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 2: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12)*

## What I Built

If you bill by the hour, your timesheet is a reconstruction. You forget to start the timer, you switch between three clients before lunch, and at the end of the month you rebuild the week from your browser history.

The tools that fix this want your money or your screen. In August, Harvest customers opened renewal bills after its sale to Bending Spoons: one user's price went from $12 a month to about $116, and a UK consultancy's monthly bill went from $130 to $2,110 ([Silicon UK](https://www.silicon.co.uk/e-enterprise/merger-acquisition/harvest-price-shock-631249)). The automatic trackers work by watching everything you do, and people don't like being watched, even locally: when Microsoft brought back Recall, [Signal](https://signal.org/blog/signal-doesnt-recall/) and [Brave](https://brave.com/privacy-updates/35-block-recall/) both shipped ways to block it by default.

**lowkey** is a timesheet that writes itself on your own laptop. Every 5 seconds it notes which window is in front: the app's name and the window's title, nothing else. No screenshots, no URLs, no keystrokes. Every 5 minutes, Gemma 4 E2B, running on my laptop's GPU through Ollama, reads that slot of window titles and decides which client it was for and what got done. You review the lines like a feed, **bill it** or **nah**, and send a PDF invoice.

It's for freelancers and small studios who bill hourly, and especially the ones under NDA, who can't paste client work into a cloud AI at all.

![The island tucked away, as a pill on hover, and fully open](https://raw.githubusercontent.com/nirajkhetre/lowkey/main/docs/images/island-states.png)

There are two faces:

- **The island**, a notch that hides in the edge of the screen as a thin line in your current client's colour. Hover and it opens: your client as a little blob creature, the session timer, what you've earned today, and your last hour drawn as a wave. It says *"switched to Nimbus Labs"* when your work changes clients, and on Windows it steps aside when a video or game goes fullscreen.
- **The dashboard** at `127.0.0.1:7777`: your day in colour blocks, one card per work session with its invoice line, a **why?** on every card that shows the windows behind it, and the invoice.

![The dashboard: the day in blocks, then one card per session](https://raw.githubusercontent.com/nirajkhetre/lowkey/main/docs/images/dashboard.png)

**Who would pay for it?** People already pay for time tracking, and the Harvest story shows what happens when the price is someone else's decision. lowkey is MIT-licensed and free to run; what I'd charge for is the boring part: a one-click installer, a signed Mac build and invoice templates.

<!-- ✏️ FILL IN (first user, part 1): one sentence on what your first user said they'd pay, in their words. Delete this comment if nobody tried it. -->

## Demo

You can run the bundled demo week without tracking anything:

```bash
ollama pull gemma4:e2b
git clone https://github.com/nirajkhetre/lowkey && cd lowkey
pip install -r requirements.txt
python -m lowkey --demo
```

![A nudge when you drift, one-tap progress when you move on, and what's next with its reason](https://raw.githubusercontent.com/nirajkhetre/lowkey/main/docs/images/island-focus.png)

![Click a gap in your day, say what it was](https://raw.githubusercontent.com/nirajkhetre/lowkey/main/docs/images/log-time.png)

## Code

{% github nirajkhetre/lowkey %}

## How I Built It

```
foreground window, every 5 s → a JSONL file on disk you can read
                                (idle 5 min+, "go dark", never_track apps: nothing is written)
     → 5-minute slots → the top 8 windows by time
     → Gemma 4 E2B on Ollama: {client, task, billable}, client constrained to an enum of your clients
     → same-client slots merge into a session → a second pass writes one invoice line
     → plain code: how much of the session your client hints actually back up
     → you: bill it / nah / move it to another client → lowkey learns a hint
     → invoice, PDF or CSV
```

Python's standard library does the tracking (`ctypes` on Windows), PySide6 paints the island, and the dashboard is one HTML file. The server binds to `127.0.0.1` and refuses pages from anywhere else. The model is called through Ollama with a JSON schema, temperature 0 and Gemma's thinking turned off.

### A small model is a confident witness

I asked Gemma for a confidence score with every label. On the 155 slots of my demo week, it said **1.0 on 152 of them**. So the number on each card isn't the model's: it's computed by plain code, as the share of the session's time whose window titles contain that client's hints (repo names, domains, project names). Under 60%, the card says *"check me"*. The model writes the line; code decides how much to trust it.

Thinking was the other surprise. Gemma 4 thinks out loud by default, and my first labelling call took **9.5 s**. With thinking off and a schema, a label takes under half a second on an RTX 4050 laptop GPU.

### How long should a slot be?

I started with 15-minute slots, because that's how I'd fill in a timesheet by hand. A slot gets one client, though, so if you spend 9 minutes on Acme and 6 on Nimbus, all 15 go to Acme. Shorter slots fix that and give the model less to read. So I measured both, on the synthetic demo week, where every window's true client is known from its title:

| Slot | Slots | Gemma picks the slot's main client | Minutes billed to the right client | Same, keyword rules | Gemma per label |
|---|---|---|---|---|---|
| 15 min | 155 | 98.1% | 91.7% | 91.3% | 487 ms |
| 10 min | 228 | 95.2% | 91.7% | 91.7% | 459 ms |
| **5 min** | 440 | 95.7% | **94.6%** | 94.1% | 460 ms |

At 5 minutes Gemma has less context and gets a few more slots wrong, but far less time gets swept into the wrong client, so more of the money lands in the right place. That's the default now, and **reads every** in the settings changes it. A day keeps the length it was first labelled with, because your approvals point at sessions by their start time; changing it mid-day waits for tomorrow if you've already reviewed something. Anyone can re-run the table: `python -m lowkey.eval`.

On my own days I can't score clients yet (more on that below), but I can measure the same effect with no model at all. Over the first 298 active minutes lowkey recorded on my laptop, with 15-minute slots **37%** of my time fell in slots that were mostly about a different app; with 5-minute slots, **28.6%**. I switch apps a lot.

At 15 minutes, Gemma's three misses on the demo week were all slots split almost exactly in half between work and personal: 50/50, 47/53 and 49/51. And look at the rules column: plain keyword matching on your hints is nearly as good at every length, because the synthetic titles contain client names. The demo week is easy on purpose. The model earns its place on real titles that don't name the client, and in the writing, which rules can't do.

### Teaching it to write a day

Above the numbers, the dashboard shows the day in a sentence, written by Gemma from the day's invoice lines, never from raw window titles. My first prompt showed it the lines with their times and asked for "how the day went, like a friend who just read it". It reported instead:

> the most time went to nimbus labs with 130 minutes spent modifying handlers.py and documenting the v2 spec.

A sharper second version asked it to lead with the day's most concrete win, and for one day Gemma handed a line straight back:

> 11:15, 147 min, Acme Studio: Fixed OAuth redirect in acme-website PR; modified auth.ts & login.tsx.

The third dropped the times from what it sees and says "your own words: never copy a line". It works, mostly:

> you nailed the oauth redirect and auth logic for acme-website. then you spent time previewing chai and working on nimbus-api tasks.

All five demo days now open with "you nailed", and one of them comes out broken: *"you nailed the login.tsx development for acme studio was a solid win"*. The session lines have the same kind of slip: I ask for no client names, and one summary still says *"modified card for Chai & Co theme"*.

### Learning from a fix, carefully

When you move a session to the right client, Gemma picks one word from that session's windows that should have told it. In my tests, given `masala-landing - Figma` filed under Chai & Co, it picked `masala-landing`; given `invoice-gen - main.py - Visual Studio Code` under Nimbus Labs, `invoice-gen`. Then plain code checks the word before it's learned: it must appear in those windows, not be generic (`chrome`, `figma`, `untitled`…) and not already be another client's hint. It needs the check. Given a slot of Reddit, a lofi stream on YouTube and a WhatsApp chat titled "Mom", filed under Chai & Co, Gemma answered `Chai & Co`, which appears in none of those titles. When it suggests nothing usable, lowkey learns nothing rather than guess. When it does learn, it says *"learned: masala-landing means Chai & Co from now on"*, with undo.

### Making the model visible

Using my own build for a day, it felt like a normal app: the model's lines looked exactly like anything I'd typed. So now a small sparkle marks everything Gemma wrote and nothing else. A pill in the header says what it's doing while it does it (*"reading 5 min of your windows…"*) and then how long it took, and the island's edge lights up in the same colours. New lines write themselves into the page. Edit one and its card says *your words* instead.

### Bugs worth telling

- **My taskbar is at the top.** The first island sat on pixel row 0, under a taskbar that is also "always on top". It now hangs from the work area, or optionally re-raises itself above the taskbar.
- **YouTube fullscreen.** The island is supposed to step aside over fullscreen video. It didn't, because my check skipped maximized windows, and Chrome still reports a window as maximized after it goes fullscreen. The difference turned out to be geometry: maximized, Chrome's window was `[-9, 31, 1929, 1089]` on a `1920×1080` screen, hanging over the edges by its invisible borders; fullscreen, it's exactly `[0, 0, 1920, 1080]`. Now a window counts as fullscreen when it fits the screen exactly.

### What the checks can't see

- **"% backed" only knows your hints.** A Zoom call or an untitled Notepad window can't back anything, so honest work there shows up as *"check me"*.
- **Half-and-half slots** are a coin flip, for Gemma and for me.
- **The day sentence isn't checked by code.** It's written from your invoice lines, never the raw windows, but nothing checks it against them, so a wrong word reaches the screen. It wears the sparkle so you know whose words they are.
- **lowkey never records URLs**, so a browser tab is only as specific as its title.
- **Daily use is on Windows 11.** The macOS and Linux trackers pass tests against recorded command output, but haven't run on real hardware yet.

### My real days

<!-- ✏️ FILL IN (real-day numbers). Set your real clients first (dashboard → C), work as usual, then review every card.
Your reviews are the ground truth: a session you move to another client is a miss, a line you rewrite is an edit.
Fill this in with what really happened, e.g.:

| My real days | Gemma 4 E2B |
|---|---|
| Work sessions reviewed | N over D days |
| Sessions I had to move to another client | M (so N−M right) |
| Invoice lines I rewrote | K of N |

Then one or two sentences: the most interesting thing it got wrong, quoted. If you didn't get to this, delete the section. -->

## Why Does Open Innovation Matter?

For lowkey it isn't a preference. It couldn't be built on a closed API.

1. **The data is the most private thing on the computer.** Window titles are client names, repo names, DM previews and the name of the clinic you booked. Sending them to a cloud model every few minutes, all day, isn't a privacy-policy question. With an open-weight model on my GPU they have nowhere to go, and you don't have to trust me: the code is open and the server only listens on `127.0.0.1`.
2. **Always-on has to be free.** At 5-minute slots that's 12 slots an hour, and the slot still filling up is re-read every minute, so up to about 60 model calls an hour, every working hour, for as long as you work. On my own GPU each one costs under half a second and nothing else.
3. **I can see and steer every step.** Ollama lets me force a JSON schema, make the client an enum so the model can't invent one, turn thinking off when it costs 9 seconds, and swap the model with one environment variable (`LOWKEY_MODEL=qwen3:4b`).
4. **Nobody can reprice it.** The weights are on my disk. No acquisition turns this into a usage-based bill.

Where a closed model would be better: the writing. A frontier model would write a livelier day sentence without opening every day with "you nailed", and it would need fewer guards. It would also need my window titles, a key, a server and a bill.

## My First User

<!-- ✏️ FILL IN (first user, part 2). ONLY what really happened:
who (a freelancer you know, no surname needed), how long they ran it, what it caught that they'd have forgotten,
what it got wrong, whether they'd pay and how much (ask a concrete price), and what they asked for next.
If nobody tried it, delete this whole section; don't invent one. -->

## Prize Categories

- **Best Use of Gemma**: Gemma 4 E2B labels every 5-minute slot, writes each invoice line and the day's sentence, sorts personal time, guesses the client for time you log by hand, and picks what to learn from your fixes, all locally through Ollama with a JSON schema, a client enum and thinking turned off.
