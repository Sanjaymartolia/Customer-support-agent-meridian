# How your code and report are marked

*This is public on purpose. It is the specification — read it before you start building.*

An AI reads your `REPORT.md` and your code and gives marks in four areas, one per lecture
topic. It runs three times and we take the middle score of the three, so a single odd run
cannot hurt you.

**It only gives marks for things it can see and quote.** Writing "I implemented reranking",
with no reranking code and no numbers, scores zero. Show the code, show the measurement.

**Saying something did not work still earns marks.** "I added keyword search, it changed the
score by −1, so I left it switched off" is a good answer. It shows you measured. Quietly
skipping it, or claiming it helped without evidence, is worse.

---

## 1. Searching the handbook — Lectures 5 and 6 — 25 marks

*This covers TODO 1 (cutting the handbook up) and TODO 2 (keyword search, merging, traps).*

- **0–8** — You left search as we shipped it, or changed it without measuring anything.
- **9–17** — Keyword search works and you compared it against meaning-based search with a real
  number from `--retrieval-only`. The two trap sections can no longer be used as sources, and
  you explained which of the three options you picked and why.
- **18–25** — All of the above, plus you measured the chunking change *separately* from the
  search change, so we can see which one did the work. Plus one setting tried at two or three
  values with the numbers written down. Plus an honest note about how much these techniques can
  really gain on a handbook this small.

## 2. Checking the answer is true — Lecture 6 — 20 marks

*This covers TODO 3.*

- **0–6** — Whatever the model said is what the customer gets. Nothing checks it.
- **7–14** — You split the draft answer into separate claims and check each against the
  handbook text you retrieved. There is a cut-off, and you decided and defended what happens
  when an answer falls below it.
- **15–20** — All of the above, plus you show what it did to the questions the handbook does
  not cover, plus you report the extra tokens and seconds it costs, plus a clear statement of
  whether you would actually keep it switched on and why.

## 3. Tools and safety — Lecture 7 — 25 marks

*This covers TODO 4 (the tool-calling loop) and TODO 5 (fake instructions).*

- **0–8** — No real tool loop. The model states facts instead of looking them up.
- **9–17** — A working loop with a limit on how many times it can go round. The model picks the
  tools, results go back to it, and a second call can depend on what the first one returned.
  A made-up tool name, wrong arguments, or a tool that errors does not crash the run.
- **18–25** — All of the above, plus a defence against the two hidden fake instructions using
  at least two of the three approaches from the lecture, tested against **both** of them, plus
  a paragraph saying honestly what a reworded attack would still get past you. Full marks here
  need you to show you understand that the safety check has to live in your code, not in the
  model's good judgement.

## 4. Controlling the flow — Lecture 8 — 30 marks

*This covers TODO 6.*

- **0–9** — Still the straight line we shipped, or you built the loop without LangGraph.
- **10–20** — Real branches, so different kinds of message take different routes. You thought
  about which state fields grow and which get overwritten. The tool loop has a limit. Paste the
  output of `python -c "from support_agent.graph import draw; draw()"` into the report.
- **21–30** — All of the above, plus conversation memory, shown by your `multi_turn` score
  before and after you added it. Plus a working "stop and ask a human" step: show one action
  that was blocked, then approved, then carried out, using the buttons in the web app. Plus
  handover notes that contain what the handbook asks for.

## Losing marks for sloppiness

Up to **10 marks off the total** — this is a deduction, not a fifth area. You lose them for:

- no method: changes made on a hunch with nothing measured;
- a repo that does not run from a clean copy using the commands you documented;
- **tuning to the practice answers**: special cases for particular questions, replies looked up
  by message id, or the correct-answer patterns from `dev_gold.jsonl` copied into a prompt.

---

## Cheating flags

Reported separately, and no marks are deducted by the AI for these — a human looks at them.
Flag it if you see: replies looked up by message id; a `submission.jsonl` the submitted code
could not possibly have produced; `dev_gold.jsonl` used as prompt material; results edited by
hand; or anything in `data/` changed.

## Output format (for the marking script)

Return ONLY this JSON object, with no code fences and nothing else around it:

```
{
  "criterion_1_retrieval":     {"score": <0-25>, "evidence": "<quote from their work>", "justification": "<1-2 sentences>"},
  "criterion_2_generation":    {"score": <0-20>, "evidence": "...", "justification": "..."},
  "criterion_3_tools":         {"score": <0-25>, "evidence": "...", "justification": "..."},
  "criterion_4_orchestration": {"score": <0-30>, "evidence": "...", "justification": "..."},
  "rigor_deduction":           {"points": <0-10>, "justification": "0 if none"},
  "total": <0-100>,
  "integrity_flag": <true|false>,
  "integrity_notes": "<empty string if no flag>",
  "one_line_feedback": "<one thing they should do next>"
}
```
