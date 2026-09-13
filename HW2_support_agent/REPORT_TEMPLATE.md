# HW2 Report — <your name>, <roll number>

*About two pages. Delete these italic notes as you go.*

*One rule: every claim needs a number or a file name next to it. The marker ignores anything it
cannot check.*

## The short version

| | score on the 24 practice questions |
|---|---|
| what we gave you | about 70 |
| what I ended up with | |

I used the model `…`, with `RETRIEVAL_MODE=…` and chunks of `…` characters.
The whole project cost me about $….

## What I changed, and what each change was worth

*Fill in the score after each change so we can see which ones actually mattered. Add rows for
anything else you tried.*

| What I did | Practice score after | Kept it? |
|---|---|---|
| (nothing yet — the starting point) | ~70 | — |
| TODO 4 — the tool-calling loop | | |
| TODO 2 — keyword search and the trap sections | | |
| TODO 3 — checking the answer is supported | | |
| TODO 6 — branches, memory, human approval | | |
| TODO 5 — defending against fake instructions | | |
| TODO 1 — cutting the handbook at its headings | | |

*Then two short paragraphs: which change made the biggest difference and why you think so, and
one thing you tried that did not work and what you think went wrong.*

## 1. Searching the handbook

*Numbers from `--retrieval-only` for: what we shipped, your chunking change, and your keyword
search. Measure them one at a time or you will not know which helped.*

*What you decided to do about the out-of-date policy section and the customer gossip section,
and why you picked that over the other two options.*

## 2. Checking the answer is true

*How you split an answer into claims and check them. What your cut-off is and what happens
below it. What it did to the questions the handbook does not cover. What it cost in tokens and
seconds. Whether you would leave it switched on.*

## 3. Tools and safety

*How your tool loop works and how you stopped it running forever. Paste one example where the
agent called a second tool because of what the first one returned.*

*What you did about the two hidden fake instructions, what happened before and after, and —
this is the part that earns the marks — what a reworded attack would still get past you.*

## 4. Controlling the flow

*Paste the output of `python -c "from support_agent.graph import draw; draw()"`.*

*Two or three sentences on your branches. Your `multi_turn` score before and after you added
conversation memory. One example of an action that was blocked, then approved by a human, then
carried out.*

*Fill this in — it shows both kinds of mistake:*

| | agent fetched a human | agent handled it alone |
|---|---|---|
| **should have fetched a human** | correct | missed — the dangerous mistake |
| **should have handled it alone** | wasted someone's time | correct |

## Evidence

*One screenshot of the web app showing the trace panel. Your score per category. One sentence
on your worst category and what you would do about it with another week.*

## How to run this

```bash
pip install -r requirements.txt && cp .env.example .env
python scripts/build_index.py --force
python scripts/run_batch.py --in data/test_queries.jsonl --out submission.jsonl
```

*Anything else needed to reproduce your numbers. And please say which AI tools you used while
doing this homework, and what you used them for.*
