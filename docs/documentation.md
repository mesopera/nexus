# Nexus

## Phase 1 Foundation Summary

### Models Being Evaluated

#### Self-Hosted via Ollama (Free, Local)
| Model | Size | Provider | Notes |
|---|---|---|---|
| LLaMA 3.1 | 8B, 70B | Meta | Excellent all-round baseline |
| Mistral | 7B | Mistral AI | Fast, efficient, good instruction following |
| Mixtral | 8x7B | Mistral AI | MoE architecture, stronger than Mistral 7B |
| Phi-3 Medium | ~14B | Microsoft | Punches above its weight on reasoning |
| Gemma 2 | 9B, 27B | Google | Strong on factual tasks |
| Qwen 2.5 | 7B, 72B | Alibaba | Notably strong on math and code |

#### Free API Tiers
| Model | Provider | Access Method | Notes |
|---|---|---|---|
| Gemini 1.5 Flash | Google | Google AI Studio API | Generous free tier, fast |
| Gemini 2.0 Flash | Google | Google AI Studio API | Latest, very capable |
| LLaMA 3.1, Mixtral, Gemma | Groq | Groq API | Free tier, extremely fast inference |
| LLaMA, Mistral, Qwen | Together AI | Together API | Free credits on signup |
| Various open models | Hugging Face | HF Inference API | Free tier, broad model access |
| Mistral Large | Mistral | La Plateforme API | Free tier available |
| Command R | Cohere | Cohere API | Free tier, strong on RAG tasks |

---

## Evaluation Domains

| # | Domain | What We're Testing |
|---|---|---|
| 1 | **Mathematical Reasoning** | Arithmetic, algebra, word problems, multi-step calculations, logic math |
| 2 | **Code Generation** | Write, debug, and explain code — multiple languages, real problems |
| 3 | **Creative Writing** | Story generation, tone control, style adaptation, narrative coherence |
| 4 | **Factual Q&A** | General knowledge accuracy, resistance to hallucination, depth of answer |
| 5 | **Summarisation** | Condense long text while retaining all key points and meaning |
| 6 | **Instruction Following** | Multi-step tasks, format constraints, rule adherence, edge cases |
| 7 | **Reasoning & Logic** | Deductive and inductive reasoning, puzzles, chain-of-thought quality |
| 8 | **Long Context Handling** | Comprehension and retrieval accuracy over very large input texts |
| 9 | **Multilingual** | Accuracy and fluency when responding in non-English languages |
| 10 | **Conversational / Chat** | Natural dialogue quality, context retention across multiple turns |

**Excluded from scope:** Multimodal, Image Generation, Agentic tasks — text-only, $0 budget

---

## Scoring Parameters

### Universal Parameters (applied to every domain)

| Parameter | Description | Scale | Method |
|---|---|---|---|
| **Accuracy / Output Quality** | Is the answer correct and the output high quality? | 1–5 | Automated + Manual |
| **Hallucination Rate** | Does it confidently state false information? | 1–5 (5 = never hallucinates) | Automated + Manual |
| **Instruction Adherence** | Does it follow all format, length, and constraint requirements? | 1–5 | Automated |
| **Consistency** | How much does quality vary across 3 runs of the same prompt? | 1–5 (5 = very consistent) | Automated |
| **Latency** | Average response time in seconds | Seconds | Automated |
| **Token Count** | Total tokens used per response (for efficiency reference) | Count | Automated |

### Domain-Specific Bonus Parameters

| Domain | Extra Parameter | Why It Matters |
|---|---|---|
| Math | Step-by-step correctness | Final answer can be right for the wrong reasons |
| Code | Does the code actually run? (pass/fail) | Quality code that errors is useless |
| Creative Writing | Human preference score | Subjective quality can't be automated |
| Factual Q&A | Source-checkable correctness | Verifiable vs. plausible-sounding answers |
| Summarisation | Key point retention rate | How much of the original meaning survives |
| Long Context | Needle-in-haystack retrieval accuracy | Pinpoints exactly how well it reads long docs |

---

## What "Best" Means Per Domain

| Domain | Primary Success Metric | Secondary Metric | Evaluation Method |
|---|---|---|---|
| **Math** | % of answers correct | Step-by-step correctness | ✅ Fully Automated |
| **Code** | % of code that runs correctly | Code quality + readability | ✅ Fully Automated |
| **Creative Writing** | Human preference score (1–5) | Narrative coherence | 👁️ Manual |
| **Factual Q&A** | Accuracy + hallucination rate combined | Depth of answer | 🔀 Mixed |
| **Summarisation** | Key point retention rate | Compression quality | 👁️ Manual |
| **Instruction Following** | % of constraints correctly followed | Edge case handling | ✅ Fully Automated |
| **Reasoning & Logic** | % of correct conclusions | Chain-of-thought quality | ✅ Fully Automated |
| **Long Context** | Needle-in-haystack retrieval accuracy | Comprehension depth | ✅ Fully Automated |
| **Multilingual** | Accuracy + fluency in target language | Cultural sensitivity | 👁️ Manual |
| **Conversational** | Human preference score (1–5) | Context retention across turns | 👁️ Manual |

### Evaluation Effort Breakdown
- ✅ **Fully Automated (6 domains):** Math, Code, Instruction Following, Reasoning & Logic, Long Context — runs as scripts on Codespaces with no manual effort
- 👁️ **Manual (3 domains):** Creative Writing, Conversational, Multilingual — you review and score outputs
- 🔀 **Mixed (1 domain):** Factual Q&A — automated scoring with manual spot-checks for hallucination verification

---

### Task 6 — Set Parameter Weights Per Domain

not all parameters matter equally in every domain

| Parameter | Math | Code | Creative | Factual QA | Summarisation | Instruction | Reasoning | Long Context | Multilingual | Conversational |
|---|---|---|---|---|---|---|---|---|---|---|
| Accuracy / Quality | 40% | 35% | 35% | 35% | 25% | 30% | 40% | 35% | 35% | 35% |
| Domain-Specific | 20% | 20% | 15% | — | 20% | 25% | 15% | 20% | 15% | 15% |
| Hallucination | 15% | 10% | 5% | 30% | 15% | 10% | 20% | 20% | 15% | 10% |
| Instruction Adh. | 10% | 15% | 20% | 15% | 15% | 35% | 10% | 10% | 15% | 15% |
| Consistency | 10% | 10% | 15% | 10% | 15% | —  | 10% | 10% | 10% | 15% |
| Latency | 5% | 10% | 10% | 10% | 10% | —  | 5% | 5% | 10% | 10% |

**Reasoning behind key decisions:**
- **Math & Reasoning** — accuracy heavily weighted, hallucination matters a lot since wrong confident answers are dangerous
- **Code** — domain-specific (does it run?) weighted high, latency matters more since devs expect fast responses
- **Creative Writing** — instruction adherence high since style/tone prompts must be followed, hallucination almost irrelevant
- **Factual QA** — hallucination is the single biggest risk, weighted highest here at 30%
- **Instruction Following** — constraint compliance is the primary metric at 35%
- **Conversational** — consistency and latency weighted higher since dialogue feel matters

---
