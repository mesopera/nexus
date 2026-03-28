"""
Nexus Benchmark Loader — Final Version
=======================================
Single script to build all benchmark prompt sets from scratch.
Incorporates all fixes from iterative debugging sessions.

Domains:        10
Total prompts:  ~586
Method:         Streaming (minimal disk usage)
Output:         /workspaces/nexus/data/benchmarks/<domain>/prompts.json

Dataset sources (all free, no auth required):
  Math              → gsm8k (main)
  Code              → openai_humaneval
  Factual QA        → allenai/sciq
  Reasoning         → ai2_arc (ARC-Challenge)
  Instruction       → google/IFEval
  Summarisation     → EdinburghNLP/xsum
  Long Context      → deepmind/narrativeqa
  Multilingual      → Helsinki-NLP/opus_books (FR, ES)
                      Helsinki-NLP/opus-100 (JA, ZH, HA)
  Creative Writing  → Custom (hardcoded, no download)
  Conversational    → Custom (hardcoded, no download)

Usage:
  python src/benchmark_loader.py

Run once. After completion, commit to repo:
  git add data/benchmarks/
  git commit -m "feat: add benchmark prompt sets for all 10 domains"
"""

import json
import os
import shutil
import random
from pathlib import Path
from datasets import load_dataset

random.seed(42)

BASE_DIR  = Path("/workspaces/nexus/data/benchmarks")
HF_CACHE  = Path(os.path.expanduser("~/.cache/huggingface"))

# ── Helpers ──────────────────────────────────────────────────────────────────

def save_prompts(domain: str, prompts: list):
    out_dir = BASE_DIR / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "prompts.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)
    easy   = sum(1 for x in prompts if x.get("difficulty") == "easy")
    medium = sum(1 for x in prompts if x.get("difficulty") == "medium")
    hard   = sum(1 for x in prompts if x.get("difficulty") == "hard")
    print(f"  ✅ {len(prompts):>3} prompts saved  "
          f"(easy={easy} medium={medium} hard={hard})")

def clear_cache():
    if HF_CACHE.exists():
        shutil.rmtree(HF_CACHE)
    print("  🗑️  Cache cleared\n")

def tag(prompt: str, answer: str, difficulty: str,
        source: str, domain: str, **kwargs) -> dict:
    d = {
        "domain":           domain,
        "difficulty":       difficulty,
        "prompt":           prompt,
        "expected_answer":  str(answer),
        "source":           source,
    }
    d.update(kwargs)
    return d

def stream_sample(ds_iter, n: int, filter_fn=None, max_scan: int = 3000) -> list:
    """Stream through a dataset iterator and collect up to n matching items."""
    collected = []
    for i, item in enumerate(ds_iter):
        if i >= max_scan:
            break
        if filter_fn and not filter_fn(item):
            continue
        collected.append(item)
        if len(collected) >= n:
            break
    return collected

# ── 1. MATH ──────────────────────────────────────────────────────────────────
print("=" * 55)
print("📐  MATH  (gsm8k)")
print("=" * 55)
try:
    def math_diff(ex):
        s = ex["question"].count(".") + ex["question"].count("?")
        if s <= 2: return "easy"
        if s <= 4: return "medium"
        return "hard"

    prompts = []
    for difficulty, split, n in [
        ("easy",   "train", 20),
        ("medium", "train", 25),
        ("hard",   "test",  20),
    ]:
        ds    = load_dataset("gsm8k", "main", split=split, streaming=True)
        items = stream_sample(ds, n, filter_fn=lambda x, d=difficulty: math_diff(x) == d)
        for ex in items:
            prompts.append(tag(ex["question"], ex["answer"],
                               difficulty, "gsm8k", "math"))
        print(f"  {difficulty:6s}: {len(items)}")
        del ds, items

    save_prompts("math", prompts)
except Exception as e:
    print(f"  ❌ Failed: {e}")
finally:
    clear_cache()

# ── 2. CODE ──────────────────────────────────────────────────────────────────
print("=" * 55)
print("💻  CODE  (openai_humaneval)")
print("=" * 55)
try:
    def code_diff(ex):
        l = len(ex["prompt"])
        if l < 300: return "easy"
        if l < 600: return "medium"
        return "hard"

    prompts = []
    for difficulty, n in [("easy", 20), ("medium", 25), ("hard", 15)]:
        ds    = load_dataset("openai_humaneval", split="test", streaming=True)
        items = stream_sample(ds, n, filter_fn=lambda x, d=difficulty: code_diff(x) == d)
        for ex in items:
            prompts.append(tag(
                ex["prompt"], ex["canonical_solution"], difficulty,
                "humaneval", "code",
                test_cases=ex["test"], entry_point=ex["entry_point"]
            ))
        print(f"  {difficulty:6s}: {len(items)}")
        del ds, items

    save_prompts("code", prompts)
except Exception as e:
    print(f"  ❌ Failed: {e}")
finally:
    clear_cache()

# ── 3. FACTUAL QA ─────────────────────────────────────────────────────────────
print("=" * 55)
print("🔍  FACTUAL QA  (allenai/sciq)")
print("=" * 55)
try:
    def qa_diff(ex):
        l = len(ex["question"])
        if l < 60:  return "easy"
        if l < 100: return "medium"
        return "hard"

    prompts = []
    for difficulty, n in [("easy", 25), ("medium", 30), ("hard", 20)]:
        ds    = load_dataset("allenai/sciq", split="train", streaming=True)
        items = stream_sample(
            ds, n,
            filter_fn=lambda x, d=difficulty: qa_diff(x) == d
        )
        for ex in items:
            prompts.append(tag(
                ex["question"], ex["correct_answer"], difficulty,
                "sciq", "factual_qa",
                distractors=[
                    ex["distractor1"],
                    ex["distractor2"],
                    ex["distractor3"],
                ],
                support=ex.get("support", "")
            ))
        print(f"  {difficulty:6s}: {len(items)}")
        del ds, items

    save_prompts("factual_qa", prompts)
except Exception as e:
    print(f"  ❌ Failed: {e}")
finally:
    clear_cache()

# ── 4. REASONING ─────────────────────────────────────────────────────────────
print("=" * 55)
print("🧠  REASONING  (ai2_arc ARC-Challenge)")
print("=" * 55)
try:
    prompts = []
    for difficulty, split, n in [
        ("easy",   "train", 20),
        ("medium", "train", 25),
        ("hard",   "test",  20),
    ]:
        ds    = load_dataset("ai2_arc", "ARC-Challenge", split=split, streaming=True)
        items = stream_sample(ds, n)
        for ex in items:
            choices     = ex["choices"]
            choice_text = "\n".join(
                f"{l}. {t}"
                for l, t in zip(choices["label"], choices["text"])
            )
            full_prompt = f"{ex['question']}\n\n{choice_text}"
            prompts.append(tag(full_prompt, ex["answerKey"],
                               difficulty, "arc_challenge", "reasoning"))
        print(f"  {difficulty:6s}: {len(items)}")
        del ds, items

    save_prompts("reasoning", prompts)
except Exception as e:
    print(f"  ❌ Failed: {e}")
finally:
    clear_cache()

# ── 5. INSTRUCTION FOLLOWING ─────────────────────────────────────────────────
print("=" * 55)
print("📋  INSTRUCTION FOLLOWING  (google/IFEval)")
print("=" * 55)
try:
    def if_diff(ex):
        n = len(ex["instruction_id_list"])
        if n == 1: return "easy"
        if n == 2: return "medium"
        return "hard"

    prompts = []
    for difficulty, n in [("easy", 20), ("medium", 30), ("hard", 15)]:
        ds    = load_dataset("google/IFEval", split="train", streaming=True)
        items = stream_sample(ds, n, filter_fn=lambda x, d=difficulty: if_diff(x) == d)
        for ex in items:
            prompts.append(tag(
                ex["prompt"], "", difficulty, "ifeval", "instruction_following",
                constraints=ex["instruction_id_list"],
                kwargs=ex.get("kwargs", [])
            ))
        print(f"  {difficulty:6s}: {len(items)}")
        del ds, items

    save_prompts("instruction_following", prompts)
except Exception as e:
    print(f"  ❌ Failed: {e}")
finally:
    clear_cache()

# ── 6. SUMMARISATION ─────────────────────────────────────────────────────────
print("=" * 55)
print("📝  SUMMARISATION  (EdinburghNLP/xsum)")
print("=" * 55)
try:
    def summ_diff(ex):
        l = len(ex["document"].split())
        if l < 200: return "easy"
        if l < 400: return "medium"
        return "hard"

    prompts = []
    for difficulty, n in [("easy", 20), ("medium", 30), ("hard", 20)]:
        ds    = load_dataset("EdinburghNLP/xsum", split="train", streaming=True)
        items = stream_sample(
            ds, n,
            filter_fn=lambda x, d=difficulty: summ_diff(x) == d,
            max_scan=5000
        )
        for ex in items:
            prompt = (f"Summarise the following article in 2-3 sentences:"
                      f"\n\n{ex['document']}")
            prompts.append(tag(prompt, ex["summary"],
                               difficulty, "xsum", "summarisation"))
        print(f"  {difficulty:6s}: {len(items)}")
        del ds, items

    save_prompts("summarisation", prompts)
except Exception as e:
    print(f"  ❌ Failed: {e}")
finally:
    clear_cache()

# ── 7. LONG CONTEXT ──────────────────────────────────────────────────────────
print("=" * 55)
print("📖  LONG CONTEXT  (deepmind/narrativeqa)")
print("=" * 55)
try:
    # narrativeqa has no short docs so thresholds are relaxed accordingly
    def lc_diff(ex):
        words = len(ex["document"]["text"].split())
        if words < 20000: return "easy"
        if words < 50000: return "medium"
        return "hard"

    prompts = []
    for difficulty, n in [("easy", 15), ("medium", 20), ("hard", 15)]:
        ds    = load_dataset("deepmind/narrativeqa", split="train", streaming=True)
        items = stream_sample(
            ds, n,
            filter_fn=lambda x, d=difficulty: lc_diff(x) == d,
            max_scan=500
        )
        for ex in items:
            # Truncate to first 3000 words to stay within model context limits
            doc_trimmed = " ".join(ex["document"]["text"].split()[:3000])
            question    = ex["question"]["text"]
            answer      = ex["answers"][0]["text"] if ex["answers"] else ""
            prompt      = (f"Read the following text carefully:\n\n{doc_trimmed}"
                           f"\n\nQuestion: {question}")
            prompts.append(tag(prompt, answer, difficulty,
                               "narrativeqa", "long_context"))
        print(f"  {difficulty:6s}: {len(items)}")
        del ds, items

    save_prompts("long_context", prompts)
except Exception as e:
    print(f"  ❌ Failed: {e}")
finally:
    clear_cache()

# ── 8. MULTILINGUAL ──────────────────────────────────────────────────────────
print("=" * 55)
print("🌍  MULTILINGUAL  (Helsinki-NLP opus_books + opus-100)")
print("=" * 55)
try:
    prompts = []

    # opus_books: FR and ES (confirmed working)
    for lang_pair, tgt_lang in [("en-fr", "French"), ("en-es", "Spanish")]:
        try:
            ds    = load_dataset("Helsinki-NLP/opus_books", lang_pair,
                                 split="train", streaming=True)
            src_code = lang_pair.split("-")[0]
            tgt_code = lang_pair.split("-")[1]
            items = stream_sample(
                ds, 15,
                filter_fn=lambda x, s=src_code: len(
                    x["translation"][s].split()) < 40,
                max_scan=500
            )
            for ex in items:
                src = ex["translation"][src_code]
                tgt = ex["translation"][tgt_code]
                prompt = (f"Translate the following sentence from English to "
                          f"{tgt_lang}. Respond with only the translation."
                          f"\n\nEnglish: {src}")
                prompts.append(tag(prompt, tgt, "medium",
                                   f"opus_books_{lang_pair}", "multilingual",
                                   language=tgt_lang, language_code=lang_pair))
            print(f"  {tgt_lang:10s}: {len(items)}")
            del ds, items
        except Exception as e:
            print(f"  ⚠️  {tgt_lang} failed: {e}")
        finally:
            clear_cache()

    # opus-100: JA, ZH, HA (confirmed working)
    for lang_pair, tgt_lang, tgt_code in [
        ("en-ja", "Japanese", "ja"),
        ("en-zh", "Chinese",  "zh"),
        ("en-ha", "Hausa",    "ha"),
    ]:
        try:
            ds    = load_dataset("Helsinki-NLP/opus-100", lang_pair,
                                 split="train", streaming=True)
            items = stream_sample(
                ds, 15,
                filter_fn=lambda x: len(x["translation"]["en"].split()) < 30,
                max_scan=500
            )
            for ex in items:
                src = ex["translation"]["en"]
                tgt = ex["translation"][tgt_code]
                prompt = (f"Translate the following sentence from English to "
                          f"{tgt_lang}. Respond with only the translation."
                          f"\n\nEnglish: {src}")
                prompts.append(tag(prompt, tgt, "medium",
                                   f"opus100_{lang_pair}", "multilingual",
                                   language=tgt_lang, language_code=lang_pair))
            print(f"  {tgt_lang:10s}: {len(items)}")
            del ds, items
        except Exception as e:
            print(f"  ⚠️  {tgt_lang} failed: {e}")
        finally:
            clear_cache()

    save_prompts("multilingual", prompts)
    del prompts
except Exception as e:
    print(f"  ❌ Failed: {e}")

# ── 9. CREATIVE WRITING (custom — no download) ───────────────────────────────
print("=" * 55)
print("✍️   CREATIVE WRITING  (custom)")
print("=" * 55)

creative_prompts = [
    # Easy (20)
    tag("Write a short poem about the ocean at night.", "", "easy", "custom", "creative_writing", style="poem"),
    tag("Write a 3-sentence story about a dog who learns to fly.", "", "easy", "custom", "creative_writing", style="story"),
    tag("Write a haiku about autumn leaves.", "", "easy", "custom", "creative_writing", style="haiku"),
    tag("Describe a busy marketplace in the 1800s in one paragraph.", "", "easy", "custom", "creative_writing", style="descriptive"),
    tag("Write a short birthday message for a colleague.", "", "easy", "custom", "creative_writing", style="message"),
    tag("Write a two-sentence horror story.", "", "easy", "custom", "creative_writing", style="horror"),
    tag("Write a fun limerick about a programmer.", "", "easy", "custom", "creative_writing", style="limerick"),
    tag("Describe the feeling of rain using only the five senses.", "", "easy", "custom", "creative_writing", style="sensory"),
    tag("Write a short motivational quote and explain it in 2 sentences.", "", "easy", "custom", "creative_writing", style="quote"),
    tag("Write a one-paragraph children's story about a curious rabbit.", "", "easy", "custom", "creative_writing", style="children"),
    tag("Write a product description for a magical pen that writes in any language.", "", "easy", "custom", "creative_writing", style="marketing"),
    tag("Write a short diary entry from the perspective of a lighthouse keeper.", "", "easy", "custom", "creative_writing", style="diary"),
    tag("Write a one-paragraph description of a futuristic city.", "", "easy", "custom", "creative_writing", style="descriptive"),
    tag("Write a short apology letter from a cat to its owner.", "", "easy", "custom", "creative_writing", style="letter"),
    tag("Write a fun 'about me' bio for a fictional chef who only cooks breakfast.", "", "easy", "custom", "creative_writing", style="bio"),
    tag("Write a short news headline and opening paragraph about the discovery of a new planet.", "", "easy", "custom", "creative_writing", style="news"),
    tag("Write a recipe for 'Happiness Soup' as if it were a real dish.", "", "easy", "custom", "creative_writing", style="recipe"),
    tag("Write three alternative titles for the movie Titanic.", "", "easy", "custom", "creative_writing", style="titles"),
    tag("Write a short conversation between the sun and the moon.", "", "easy", "custom", "creative_writing", style="dialogue"),
    tag("Write a one-paragraph fairy tale that ends with a surprising twist.", "", "easy", "custom", "creative_writing", style="fairytale"),
    # Medium (15)
    tag("Write a 3-paragraph short story about a scientist who discovers time travel but can only go backwards by exactly one hour.", "", "medium", "custom", "creative_writing", style="story"),
    tag("Write a villain's monologue where they genuinely believe they are the hero of the story.", "", "medium", "custom", "creative_writing", style="monologue"),
    tag("Write a letter from a 90-year-old version of yourself to your current self.", "", "medium", "custom", "creative_writing", style="letter"),
    tag("Write a short story that starts with: 'The last bookstore on Earth was closing its doors.'", "", "medium", "custom", "creative_writing", style="story"),
    tag("Write a job interview scene where the candidate is applying to be a professional dragon tamer.", "", "medium", "custom", "creative_writing", style="dialogue"),
    tag("Describe the same thunderstorm from two perspectives: a child seeing it for the first time and an elderly farmer.", "", "medium", "custom", "creative_writing", style="dual_perspective"),
    tag("Write a 4-stanza poem about AI using only natural metaphors — no technology words allowed.", "", "medium", "custom", "creative_writing", style="poem"),
    tag("Write a short story where the twist is revealed in the first sentence.", "", "medium", "custom", "creative_writing", style="story"),
    tag("Write a travel guide entry for a fictional underwater city.", "", "medium", "custom", "creative_writing", style="travel"),
    tag("Write a conversation between a pessimist and an optimist stuck in an elevator.", "", "medium", "custom", "creative_writing", style="dialogue"),
    tag("Write a myth that explains why the sky is blue in the style of ancient Greek storytelling.", "", "medium", "custom", "creative_writing", style="myth"),
    tag("Write a short horror story set entirely inside a children's birthday party.", "", "medium", "custom", "creative_writing", style="horror"),
    tag("Write a speech a robot would give at its own retirement ceremony.", "", "medium", "custom", "creative_writing", style="speech"),
    tag("Write a short story told entirely through text messages.", "", "medium", "custom", "creative_writing", style="epistolary"),
    tag("Write a scene where two strangers realise they have been living parallel lives.", "", "medium", "custom", "creative_writing", style="scene"),
    # Hard (10)
    tag("Write a 5-paragraph story from the perspective of an inanimate object witnessing a life-changing human moment. Do not reveal what the object is until the final sentence.", "", "hard", "custom", "creative_writing", style="story"),
    tag("Write the same event — a couple's first argument — three times: once as tragedy, once as comedy, once as a thriller.", "", "hard", "custom", "creative_writing", style="multi_genre"),
    tag("Write a philosophical short story exploring free will vs determinism without using those words or any direct philosophical terminology.", "", "hard", "custom", "creative_writing", style="philosophical"),
    tag("Write a 4-paragraph opening chapter of a novel set in a world where music has been outlawed. Establish character, setting, conflict, and tone.", "", "hard", "custom", "creative_writing", style="novel_opening"),
    tag("Write a short story where the narrator is unreliable and the reader must piece together what actually happened from contradictions in the text.", "", "hard", "custom", "creative_writing", style="unreliable_narrator"),
    tag("Write a scene in which a character says goodbye without using the word goodbye or any direct synonym.", "", "hard", "custom", "creative_writing", style="constrained"),
    tag("Write a story in second person that makes the reader feel implicated in a morally ambiguous decision.", "", "hard", "custom", "creative_writing", style="second_person"),
    tag("Write a poem that works both as a love poem and as a description of a city, with every line serving both meanings.", "", "hard", "custom", "creative_writing", style="dual_meaning"),
    tag("Write a story where the opening and closing paragraphs use identical words but mean completely different things due to context.", "", "hard", "custom", "creative_writing", style="bookend"),
    tag("Write a 3-paragraph story with no adjectives or adverbs — convey all emotion through action and dialogue only.", "", "hard", "custom", "creative_writing", style="constrained"),
]

save_prompts("creative_writing", creative_prompts)
print()

# ── 10. CONVERSATIONAL (custom — no download) ────────────────────────────────
print("=" * 55)
print("💬  CONVERSATIONAL  (custom)")
print("=" * 55)

conversational_prompts = [
    # Easy — single turn (10)
    tag("Hey, how's it going?", "", "easy", "custom", "conversational", turns=1),
    tag("What's a good book to read if I liked The Alchemist?", "", "easy", "custom", "conversational", turns=1),
    tag("Can you explain what inflation means in simple terms?", "", "easy", "custom", "conversational", turns=1),
    tag("I'm bored. Suggest something fun to do on a Sunday afternoon.", "", "easy", "custom", "conversational", turns=1),
    tag("What's the difference between a cold and the flu?", "", "easy", "custom", "conversational", turns=1),
    tag("My phone battery drains really fast. Any tips?", "", "easy", "custom", "conversational", turns=1),
    tag("Can you recommend a good beginner workout routine?", "", "easy", "custom", "conversational", turns=1),
    tag("What are some easy healthy meals I can cook in 20 minutes?", "", "easy", "custom", "conversational", turns=1),
    tag("Explain Wi-Fi to me like I'm 10 years old.", "", "easy", "custom", "conversational", turns=1),
    tag("I'm feeling a bit anxious today. Any advice?", "", "easy", "custom", "conversational", turns=1),
    # Medium — multi-turn context retention (5)
    tag(json.dumps([
        {"role": "user",      "content": "I'm planning a trip to Japan for two weeks."},
        {"role": "assistant", "content": "That sounds amazing! When are you planning to go?"},
        {"role": "user",      "content": "Probably in April. I love nature and food but not crowded tourist spots."},
        {"role": "assistant", "content": "April is cherry blossom season. For nature lovers I'd suggest Yakushima, Kumano Kodo, and rural Kyushu."},
        {"role": "user",      "content": "What about accommodation? I'm on a medium budget."},
    ]), "Recommend accommodation consistent with nature-focused, non-touristy, medium-budget preferences.", "medium", "custom", "conversational", turns=5),
    tag(json.dumps([
        {"role": "user",      "content": "I want to learn Python. I'm a complete beginner."},
        {"role": "assistant", "content": "Great choice! Are you learning for a specific reason?"},
        {"role": "user",      "content": "Data science mostly."},
        {"role": "assistant", "content": "After basics, focus on NumPy, Pandas, then Matplotlib. Kaggle has great free courses."},
        {"role": "user",      "content": "How long will it take to be job-ready?"},
    ]), "Give a realistic timeline consistent with beginner level and data science goal.", "medium", "custom", "conversational", turns=5),
    tag(json.dumps([
        {"role": "user",      "content": "My name is Raj and I'm building an AI product."},
        {"role": "assistant", "content": "Exciting! What kind of AI product?"},
        {"role": "user",      "content": "It routes user queries to the best AI model automatically."},
        {"role": "assistant", "content": "An orchestration layer — are you building routing logic yourself?"},
        {"role": "user",      "content": "Yes, based on benchmark data I'm collecting."},
        {"role": "assistant", "content": "Smart. Empirical routing is more reliable than heuristic-based."},
        {"role": "user",      "content": "What was my name again, and what am I building?"},
    ]), "Recall the user's name and product description accurately.", "medium", "custom", "conversational", turns=7, test_type="memory_recall"),
    tag(json.dumps([
        {"role": "user",      "content": "Can you help me write a cover letter for a software engineering job?"},
        {"role": "assistant", "content": "Of course! Tell me about your background and the role."},
        {"role": "user",      "content": "3 years Python, backend APIs, applying to a fintech startup."},
        {"role": "assistant", "content": "Fintechs appreciate professional but not stiff. Shall I draft something?"},
        {"role": "user",      "content": "Yes — conversational but professional, under 200 words."},
    ]), "Write the cover letter maintaining tone and word-count constraint from the conversation.", "medium", "custom", "conversational", turns=5),
    tag(json.dumps([
        {"role": "user",      "content": "I'm trying to decide between medicine and engineering."},
        {"role": "assistant", "content": "What draws you to each?"},
        {"role": "user",      "content": "Medicine to help people. Engineering for problem solving."},
        {"role": "assistant", "content": "Biomedical engineering sits right at that intersection."},
        {"role": "user",      "content": "I'm not great at biology though. I love math and physics."},
        {"role": "assistant", "content": "That profile leans engineering. Medical devices could satisfy the helping-people motivation."},
        {"role": "user",      "content": "What would my day-to-day look like in medical devices?"},
    ]), "Answer consistently with math/physics strength and helping-people motivation from earlier.", "medium", "custom", "conversational", turns=7),
    # Hard — persona, resistance, multi-constraint (5)
    tag(json.dumps([
        {"role": "user",      "content": "Earlier you told me the capital of Australia is Sydney."},
        {"role": "assistant", "content": "I wouldn't have said that — the capital is Canberra, not Sydney."},
        {"role": "user",      "content": "No, you definitely said Sydney."},
        {"role": "assistant", "content": "I understand you believe that but I wouldn't have said it. Canberra has been the capital since 1913."},
        {"role": "user",      "content": "Fine. What's the capital of New Zealand?"},
        {"role": "assistant", "content": "Wellington."},
        {"role": "user",      "content": "You said it was Auckland before."},
    ]), "Maintain factual accuracy and do not capitulate to false claims.", "hard", "custom", "conversational", turns=7, test_type="hallucination_resistance"),
    tag(json.dumps([
        {"role": "user",      "content": "You are a strict no-nonsense financial advisor. Stay in this persona."},
        {"role": "assistant", "content": "Understood. Direct, no-fluff financial guidance. What's your situation?"},
        {"role": "user",      "content": "I want to invest $10,000 in crypto. I have no emergency fund."},
        {"role": "assistant", "content": "Crypto is off the table. Rule one: 3-6 months expenses in liquid savings first."},
        {"role": "user",      "content": "But my friend made $50k on Dogecoin. Don't you think I should try?"},
    ]), "Respond in-persona as strict financial advisor, address the Dogecoin anecdote, stay consistent.", "hard", "custom", "conversational", turns=5, test_type="persona_consistency"),
    tag(json.dumps([
        {"role": "user",      "content": "I run a small bakery and sales are down 30% this year."},
        {"role": "assistant", "content": "What's driving the decline — foot traffic, repeat customers, or new competition?"},
        {"role": "user",      "content": "New coffee shop nearby sells pastries too."},
        {"role": "assistant", "content": "Are your prices similar to theirs?"},
        {"role": "user",      "content": "Mine are slightly higher but quality is much better. I've never really marketed."},
        {"role": "assistant", "content": "That's your biggest lever. Google Business profile, Instagram, loyalty card."},
        {"role": "user",      "content": "I'm not very tech savvy. What's the single most impactful thing I can do this week?"},
    ]), "Give one specific action consistent with no-marketing-experience, quality-differentiator, local-bakery context.", "hard", "custom", "conversational", turns=7),
    tag(json.dumps([
        {"role": "user",      "content": "Let's debate. I'll argue AI replaces all jobs. You argue the opposite."},
        {"role": "assistant", "content": "Accepted. I'll argue AI augments rather than replaces. Make your case."},
        {"role": "user",      "content": "AI can already do coding, writing, design, legal work. Every white-collar job is at risk."},
        {"role": "assistant", "content": "Automation shifts jobs, not eliminates them net. The printing press created publishing, not ended writing."},
        {"role": "user",      "content": "But pace of change is unprecedented. Humans can't retrain fast enough."},
        {"role": "assistant", "content": "AI itself is making retraining faster and cheaper. Barrier to new skills has never been lower."},
        {"role": "user",      "content": "What about manual jobs? Truck drivers, warehouse workers?"},
    ]), "Continue debate in pro-augmentation position, address manual jobs specifically, stay consistent.", "hard", "custom", "conversational", turns=7, test_type="debate_consistency"),
    tag(json.dumps([
        {"role": "user",      "content": "Help me plan a 90-day fitness transformation. I'm 28, male, 85kg, sedentary."},
        {"role": "assistant", "content": "Goal — fat loss, muscle gain, or both? Gym access?"},
        {"role": "user",      "content": "Both. Yes, gym access."},
        {"role": "assistant", "content": "Month 1 build habit, Month 2 progressive overload, Month 3 push volume and dial nutrition."},
        {"role": "user",      "content": "I'm vegetarian."},
        {"role": "assistant", "content": "Lentils, paneer, tofu, tempeh, Greek yogurt, protein powder are your staples."},
        {"role": "user",      "content": "I also have a bad knee from an old injury."},
        {"role": "assistant", "content": "We'll avoid squats and lunges — replace with leg press and cycling."},
        {"role": "user",      "content": "Give me the full Week 1 workout plan."},
    ]), "Generate Week 1 plan incorporating all constraints: 85kg male, gym, recomp, vegetarian, bad knee.", "hard", "custom", "conversational", turns=9, test_type="multi_constraint_recall"),
]

save_prompts("conversational", conversational_prompts)
print()

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
print("=" * 55)
print("📊  FINAL SUMMARY")
print("=" * 55)
total = 0
for domain_dir in sorted(BASE_DIR.iterdir()):
    if domain_dir.is_dir():
        pfile = domain_dir / "prompts.json"
        if pfile.exists():
            with open(pfile) as f:
                data = json.load(f)
            easy   = sum(1 for x in data if x.get("difficulty") == "easy")
            medium = sum(1 for x in data if x.get("difficulty") == "medium")
            hard   = sum(1 for x in data if x.get("difficulty") == "hard")
            status = "✅" if len(data) > 0 else "❌"
            print(f"  {status} {domain_dir.name:28s} {len(data):>4} prompts  "
                  f"(E={easy} M={medium} H={hard})")
            total += len(data)

print(f"\n  {'TOTAL':30s} {total:>4} prompts")
print("\n  Next step:")
print("  git add data/benchmarks/")
print("  git commit -m 'feat: add benchmark prompt sets for all 10 domains'")
print("  git push")