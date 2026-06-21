# HiveSense - 3-minute demo video script

A shot-by-shot script for a ~3:00 recording. Each scene has **ON SCREEN** (what to show),
**DO** (clicks/commands), and **SAY** (voiceover, ~140 words/min so it fits). Honest throughout.

---

## Prep before recording (5 min, off-camera)
```powershell
# 1. data in Redis (the unimodal memory) - run once
python scripts/seed_redis_unimodal.py        # -> "336 fused unimodal vectors indexed"
python scripts/redis_smoke.py                 # -> ALL PASS (sanity)

# 2. start the backend + dashboard (two terminals)
python api_server.py                          # reads .env -> Redis-backed, serves :8000
cd frontend; npm run dev                      # dashboard on the printed localhost URL

# 3. have these tabs/windows open and ready:
#    - the dashboard (browser)
#    - your Redis Cloud console (RedisInsight) showing the keys
#    - a terminal in the project folder
#    - notebooks/redis_unimodal_showcase.ipynb (optional, for the plots)
```
Tip: pre-run `python scripts/redis_show.py --hive B1` once so the PNG exists if you want to cut to it.

---

## Scene 1 - Hook & problem  (0:00-0:25)
**ON SCREEN:** a hive / the alcohol-wash test image, then the dashboard overview.
**SAY:**
> "To check a hive for varroa mites today, the standard test is an alcohol wash: you scoop out about
> **300 bees and kill them**, just to get one mite reading. It's lethal, invasive, and slow. HiveSense
> checks hive health **without opening the hive and without killing a single bee**, using two signals:
> the **sound** inside and a **camera** at the entrance. Here's the whole apiary, live."

## Scene 2 - The live dashboard  (0:25-0:55)
**ON SCREEN:** click into one hive card; show varroa status, acoustic-vs-vision, the operations log.
**SAY:**
> "Each hive shows a verdict - varroa, queenless, swarm risk - with the **acoustic stress** and the
> **camera mite-rate** side by side. The system is honest: when the two signals **disagree**, it
> doesn't guess - it flags **'needs a human'** and asks the beekeeper to inspect. No false confidence."

## Scene 3 - The agentic brain  (0:55-1:25)
**ON SCREEN:** the operations log scrolling (or the architecture diagram from the README).
**SAY:**
> "Under the hood, seven **Fetch.ai agents** - one per hive - each run the cheap audio check every
> cycle, then *decide* whether it's worth spending the expensive camera test, and reconcile the two.
> A coordinator, the **Godfather**, watches all seven for things no single hive can see - a regional
> varroa outbreak, or one hive robbing its neighbour. And you can just **ask it in plain English**:
> *'how are my bees?'* through the ASI:One chat."

## Scene 4 - The Redis unimodal memory  ⭐ (1:25-2:15)
**ON SCREEN:** switch to the **Redis Cloud console**; show the `hs:reading:*` keys and the `vec` field.
**SAY:**
> "Here's where Redis comes in. Every hive reading - sound **and** sight - is fused into **one
> vector**, a single fingerprint of that moment, stored in Redis. That gives the AI a **memory**."

**DO:** switch to terminal, run:
```powershell
python scripts/redis_show.py --hive B1
```
**ON SCREEN:** the printed nearest states + the saved fingerprint PNG.
**SAY:**
> "One Redis search finds the **most similar moments from the past**. So before the agent alarms the
> beekeeper, it can recall: *'this looks just like a reading we confirmed last week was a false
> alarm.'* That retrieval is what makes the alerts trustworthy - and Redis does the similarity search
> **and** the 'only this hive' filter in a **single query**."

## Scene 5 - Speed (the sponsor's question)  (2:15-2:45)
**ON SCREEN:** terminal, run the benchmark; point at the (b) section.
```powershell
python bench/redis_bench.py --n 300
```
**SAY:**
> "And it's efficient. Because it's **one fused vector**, a retrieval is **one search instead of two**
> - about **2× fewer round-trips**, measured live. Our older file approach got slower as history grew;
> Redis stays flat. We're honest: a single tiny read on *cloud* Redis isn't faster than a local file -
> the real win is the search itself, which the old store couldn't do at all, and doing it in half the
> queries."

## Scene 6 - Close & what's next  (2:45-3:00)
**ON SCREEN:** back to the dashboard, or the notebook's similarity heatmap.
**SAY:**
> "So: non-invasive, multimodal, honest about its limits - with a Redis-powered memory that makes the
> agents smarter. Next, we swap our fused vector for a fully **bound** ImageBind space, so you could
> even search by sound and retrieve by sight. That's HiveSense."

---

## Honest lines to keep ready (if a sponsor probes)
- **Speed:** "We don't claim a single cloud-Redis op beats a local file - there's a ~20 ms network
  hop. The wins are: retrieval in 1 query vs 2 (~2× fewer round-trips), flat writes as data grows,
  and similarity search the file store can't do at all."
- **'Where are the images?'** "We store the fused **vector**, not an image - storing images wasted
  memory. We render the fingerprint visual on demand."
- **Data:** "The apiary feed is simulated, but the agents, the models, and the Redis memory are real
  - real reasoning over a simulated feed."

## One-line pitch
> "Each hive reading becomes one fused fingerprint in Redis, giving our bee-AI a memory: it
> recognizes 'I've seen this before' in a single query - something separate vectors and a plain DB
> can't do as cheaply."
