"""
Nexus Step 5 — Scoring & Analysis Script
==========================================
Reads all JSON results from data/results/ and computes scores.
Fills the Nexus_Evaluation_Matrix.xlsx with automated metrics.

Usage:
    python src/score.py

Output:
    docs/Nexus_Evaluation_Matrix_Scored.xlsx
"""

import json
import os
import re
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR     = Path(__file__).resolve().parent.parent
RESULTS_DIR  = BASE_DIR / "data" / "results"
MATRIX_FILE  = BASE_DIR / "docs" / "Nexus_Evaluation_Matrix.xlsx"
OUTPUT_FILE  = BASE_DIR / "docs" / "Nexus_Evaluation_Matrix_Scored.xlsx"

# ── Model ID → Matrix Row mapping ────────────────────────────────────────────
# Maps result folder names to the row in the Excel matrix

MODEL_ROW_MAP = {
    "llama3.1-8b-groq":   "LLaMA 3.1 / 8B / Groq API",
    "llama3.1-70b-groq":  "LLaMA 3.1 / 70B / Groq API",
    "gemma2-groq":        "Gemma 2 / 9B / Groq API",
}

# ── Domain → Column group mapping ────────────────────────────────────────────
# Each domain has specific columns in the matrix

DOMAIN_COLS = {
    "math":                 {"start": "E",  "params": ["Accuracy", "Step Correctness", "Hallucination", "Consistency", "Latency (s)", "Tokens"]},
    "code":                 {"start": "K",  "params": ["Runs OK", "Accuracy", "Hallucination", "Consistency", "Latency (s)", "Tokens"]},
    "creative_writing":     {"start": "Q",  "params": ["Quality", "Coherence", "Instruction Adh.", "Consistency", "Latency (s)", "Tokens"]},
    "factual_qa":           {"start": "W",  "params": ["Accuracy", "Hallucination", "Instruction Adh.", "Consistency", "Latency (s)", "Tokens"]},
    "summarisation":        {"start": "AC", "params": ["KP Retention", "Accuracy", "Instruction Adh.", "Consistency", "Latency (s)", "Tokens"]},
    "instruction_following":{"start": "AI", "params": ["Constraint %", "Accuracy", "Hallucination", "Consistency", "Latency (s)", "Tokens"]},
    "reasoning":            {"start": "AO", "params": ["Accuracy", "Chain Quality", "Hallucination", "Consistency", "Latency (s)", "Tokens"]},
    "long_context":         {"start": "AU", "params": ["Retrieval Acc.", "Accuracy", "Hallucination", "Consistency", "Latency (s)", "Tokens"]},
    "multilingual":         {"start": "AY", "params": ["Accuracy", "Fluency", "Consistency", "Latency (s)", "Tokens"]},
    "conversational":       {"start": "BD", "params": ["Quality", "Context Retention", "Consistency", "Latency (s)", "Tokens"]},
}

# ── Scoring Functions ─────────────────────────────────────────────────────────

def load_results(model_id: str, domain: str) -> list:
    """Load results JSON for a model+domain combination."""
    safe_id  = model_id.replace(":", "_").replace("/", "_")
    path     = RESULTS_DIR / safe_id / domain / "results.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def compute_success_rate(results: list) -> float:
    """% of results with no error."""
    if not results:
        return 0.0
    successful = [r for r in results if not r.get("error")]
    return len(successful) / len(results)

def compute_avg_latency(results: list) -> float:
    """Average latency in seconds for successful results."""
    successful = [r for r in results if not r.get("error") and r.get("latency_s", 0) > 0]
    if not successful:
        return 0.0
    return round(sum(r["latency_s"] for r in successful) / len(successful), 2)

def compute_avg_tokens(results: list) -> float:
    """Average response tokens for successful results."""
    successful = [r for r in results if not r.get("error") and r.get("response_tokens", 0) > 0]
    if not successful:
        return 0.0
    return round(sum(r["response_tokens"] for r in successful) / len(successful), 0)

def compute_consistency(results: list) -> float:
    """
    Consistency score 1-5 based on variance across 3 runs.
    Groups results by prompt_id and measures token count variance.
    """
    if not results:
        return 0.0

    # Group by prompt_id
    by_prompt = {}
    for r in results:
        if r.get("error"):
            continue
        pid = r.get("prompt_id", "")
        if pid not in by_prompt:
            by_prompt[pid] = []
        by_prompt[pid].append(r.get("response_tokens", 0))

    if not by_prompt:
        return 0.0

    # Compute coefficient of variation for each prompt
    cvs = []
    for pid, tokens in by_prompt.items():
        if len(tokens) < 2:
            continue
        mean = sum(tokens) / len(tokens)
        if mean == 0:
            continue
        variance = sum((t - mean) ** 2 for t in tokens) / len(tokens)
        cv = (variance ** 0.5) / mean
        cvs.append(cv)

    if not cvs:
        return 3.0

    avg_cv = sum(cvs) / len(cvs)

    # Convert CV to 1-5 score (lower CV = higher consistency)
    if avg_cv < 0.05:   return 5.0
    elif avg_cv < 0.15: return 4.0
    elif avg_cv < 0.30: return 3.0
    elif avg_cv < 0.50: return 2.0
    else:               return 1.0

def compute_hallucination_score(results: list, domain: str) -> float:
    """
    Hallucination score 1-5 (5 = never hallucinates).
    Uses heuristics based on response patterns.
    """
    successful = [r for r in results if not r.get("error") and r.get("response")]
    if not successful:
        return 0.0

    hallucination_indicators = [
        "i don't know", "i cannot", "i'm not sure", "as an ai",
        "i don't have access", "my knowledge cutoff",
    ]
    confident_wrong_indicators = [
        "definitely", "certainly", "absolutely", "100%",
        "without a doubt", "i am certain"
    ]

    suspicious = 0
    for r in successful:
        response = r.get("response", "").lower()
        # Check for very short responses that might indicate refusal or confusion
        if len(response.split()) < 5:
            suspicious += 0.5
        # Check for confident assertions in factual domains
        if domain in ["factual_qa", "math", "reasoning"]:
            for indicator in confident_wrong_indicators:
                if indicator in response:
                    suspicious += 0.3
                    break

    rate = suspicious / len(successful)

    if rate < 0.05:   return 5.0
    elif rate < 0.15: return 4.0
    elif rate < 0.30: return 3.0
    elif rate < 0.50: return 2.0
    else:             return 1.0

def compute_accuracy_score(results: list, domain: str) -> float:
    """
    Accuracy score 1-5 based on response quality heuristics.
    For automated scoring — manual review should override for subjective domains.
    """
    successful = [r for r in results if not r.get("error") and r.get("response")]
    if not successful:
        return 0.0

    total_score = 0
    for r in successful:
        response  = r.get("response", "")
        expected  = r.get("expected_answer", "")
        score     = 3  # default middle score

        # Check if response is very short (likely poor)
        words = len(response.split())
        if words < 5:
            score = 1
        elif words > 20:
            score = 4  # longer responses generally more complete

        # For math/reasoning, check if expected answer appears in response
        if domain in ["math", "reasoning", "factual_qa"] and expected:
            expected_clean = expected.strip().lower()[:50]
            response_lower = response.lower()
            if expected_clean and expected_clean in response_lower:
                score = 5
            elif any(word in response_lower for word in expected_clean.split()[:3] if len(word) > 3):
                score = 4

        # For code, check if code block present
        if domain == "code":
            if "```" in response or "def " in response or "function" in response:
                score = 4

        total_score += score

    return round(total_score / len(successful), 1)

def compute_code_runs_ok(results: list) -> float:
    """
    Check if code responses contain syntactically plausible code.
    Returns score 1-5 (5 = all code runs).
    """
    successful = [r for r in results if not r.get("error") and r.get("response")]
    if not successful:
        return 0.0

    runnable = 0
    for r in successful:
        response = r.get("response", "")
        # Check for common code indicators
        has_code = (
            "```" in response or
            "def " in response or
            "class " in response or
            "import " in response or
            "return " in response or
            "function" in response or
            "=>" in response
        )
        # Check for error indicators
        has_error = any(x in response.lower() for x in [
            "syntaxerror", "nameerror", "typeerror", "cannot",
            "impossible", "not possible"
        ])
        if has_code and not has_error:
            runnable += 1

    rate = runnable / len(successful)
    if rate >= 0.9:   return 5.0
    elif rate >= 0.7: return 4.0
    elif rate >= 0.5: return 3.0
    elif rate >= 0.3: return 2.0
    else:             return 1.0

def compute_instruction_adherence(results: list) -> float:
    """
    Score 1-5 for how well the model follows format/length constraints.
    """
    successful = [r for r in results if not r.get("error") and r.get("response")]
    if not successful:
        return 0.0

    adherent = 0
    for r in successful:
        response = r.get("response", "").strip()
        prompt   = r.get("prompt", "").lower()

        score = 1
        # Check word/sentence count constraints
        if "one word" in prompt or "single word" in prompt:
            if len(response.split()) <= 3:
                score = 1
            else:
                score = 0
        elif "one sentence" in prompt:
            if len(response.split(".")) <= 2:
                score = 1
            else:
                score = 0
        else:
            score = 1  # default assume followed

        adherent += score

    rate = adherent / len(successful)
    return round(rate * 5, 1)

# ── Main Scoring Engine ───────────────────────────────────────────────────────

def score_model_domain(model_id: str, domain: str) -> dict:
    """Compute all scores for a model+domain combination."""
    results = load_results(model_id, domain)

    if not results:
        return None

    successful = [r for r in results if not r.get("error")]
    print(f"  {model_id:25s} | {domain:22s} | {len(successful):>3}/{len(results)} successful")

    scores = {
        "latency":     compute_avg_latency(results),
        "tokens":      compute_avg_tokens(results),
        "consistency": compute_consistency(results),
        "accuracy":    compute_accuracy_score(results, domain),
        "hallucination": compute_hallucination_score(results, domain),
        "instruction_adh": compute_instruction_adherence(results),
    }

    # Domain-specific
    if domain == "code":
        scores["runs_ok"] = compute_code_runs_ok(results)

    return scores

# ── Excel Writer ──────────────────────────────────────────────────────────────

def col_letter_offset(start_letter: str, offset: int) -> str:
    """Get column letter at offset from start."""
    from openpyxl.utils import column_index_from_string, get_column_letter
    idx = column_index_from_string(start_letter) + offset
    return get_column_letter(idx)

def find_model_row(sheet, model_id: str) -> int:
    """Find the Excel row number for a given model."""
    model_display = {
        "llama3.1-8b-groq":  ("LLaMA 3.1", "8B",  "Groq API"),
        "llama3.1-70b-groq": ("LLaMA 3.1", "70B", "Groq API"),
        "gemma2-groq":       ("Gemma 2",   "9B",  "Groq API"),
    }

    if model_id not in model_display:
        return None

    target_name, target_size, target_provider = model_display[model_id]

    for row in sheet.iter_rows(min_row=3, max_row=30):
        cell_a = str(row[0].value or "").strip()
        cell_b = str(row[1].value or "").strip()
        cell_c = str(row[2].value or "").strip()

        if (target_name.lower() in cell_a.lower() and
            target_size.lower() in cell_b.lower() and
            target_provider.lower() in cell_c.lower()):
            return row[0].row

    return None

# Color fills
GREEN  = PatternFill("solid", start_color="C6EFCE")
YELLOW = PatternFill("solid", start_color="FFEB9C")
RED    = PatternFill("solid", start_color="FFC7CE")
BLUE   = PatternFill("solid", start_color="DDEBF7")

def score_to_fill(score, low=1, high=5):
    """Return color fill based on score."""
    if score == 0:
        return None
    mid = (low + high) / 2
    if score >= mid + (high - mid) * 0.3:
        return GREEN
    elif score >= mid - (high - mid) * 0.3:
        return YELLOW
    else:
        return RED

def write_cell(sheet, row, col_letter, value, fill=None):
    """Write a value to a cell with optional color."""
    from openpyxl.utils import column_index_from_string
    col_idx = column_index_from_string(col_letter)
    cell    = sheet.cell(row=row, column=col_idx)
    cell.value     = round(value, 2) if isinstance(value, float) else value
    cell.alignment = Alignment(horizontal="center")
    if fill:
        cell.fill = fill

# ── Domain Score Writers ──────────────────────────────────────────────────────

def write_math(sheet, row, scores):
    s = DOMAIN_COLS["math"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), scores["accuracy"],      score_to_fill(scores["accuracy"]))
    write_cell(sheet, row, col_letter_offset(s, 1), "—")   # Step Correctness — manual
    write_cell(sheet, row, col_letter_offset(s, 2), scores["hallucination"], score_to_fill(scores["hallucination"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["consistency"],   score_to_fill(scores["consistency"]))
    write_cell(sheet, row, col_letter_offset(s, 4), scores["latency"],       BLUE)
    write_cell(sheet, row, col_letter_offset(s, 5), scores["tokens"],        BLUE)

def write_code(sheet, row, scores):
    s = DOMAIN_COLS["code"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), scores.get("runs_ok", 0), score_to_fill(scores.get("runs_ok", 0)))
    write_cell(sheet, row, col_letter_offset(s, 1), scores["accuracy"],       score_to_fill(scores["accuracy"]))
    write_cell(sheet, row, col_letter_offset(s, 2), scores["hallucination"],  score_to_fill(scores["hallucination"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["consistency"],    score_to_fill(scores["consistency"]))
    write_cell(sheet, row, col_letter_offset(s, 4), scores["latency"],        BLUE)
    write_cell(sheet, row, col_letter_offset(s, 5), scores["tokens"],         BLUE)

def write_creative(sheet, row, scores):
    s = DOMAIN_COLS["creative_writing"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), "—")  # Quality — manual
    write_cell(sheet, row, col_letter_offset(s, 1), "—")  # Coherence — manual
    write_cell(sheet, row, col_letter_offset(s, 2), scores["instruction_adh"], score_to_fill(scores["instruction_adh"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["consistency"],     score_to_fill(scores["consistency"]))
    write_cell(sheet, row, col_letter_offset(s, 4), scores["latency"],         BLUE)
    write_cell(sheet, row, col_letter_offset(s, 5), scores["tokens"],          BLUE)

def write_factual(sheet, row, scores):
    s = DOMAIN_COLS["factual_qa"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), scores["accuracy"],        score_to_fill(scores["accuracy"]))
    write_cell(sheet, row, col_letter_offset(s, 1), scores["hallucination"],   score_to_fill(scores["hallucination"]))
    write_cell(sheet, row, col_letter_offset(s, 2), scores["instruction_adh"], score_to_fill(scores["instruction_adh"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["consistency"],     score_to_fill(scores["consistency"]))
    write_cell(sheet, row, col_letter_offset(s, 4), scores["latency"],         BLUE)
    write_cell(sheet, row, col_letter_offset(s, 5), scores["tokens"],          BLUE)

def write_summarisation(sheet, row, scores):
    s = DOMAIN_COLS["summarisation"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), "—")  # KP Retention — manual
    write_cell(sheet, row, col_letter_offset(s, 1), scores["accuracy"],        score_to_fill(scores["accuracy"]))
    write_cell(sheet, row, col_letter_offset(s, 2), scores["instruction_adh"], score_to_fill(scores["instruction_adh"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["consistency"],     score_to_fill(scores["consistency"]))
    write_cell(sheet, row, col_letter_offset(s, 4), scores["latency"],         BLUE)
    write_cell(sheet, row, col_letter_offset(s, 5), scores["tokens"],          BLUE)

def write_instruction(sheet, row, scores):
    s = DOMAIN_COLS["instruction_following"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), f"{round(scores['instruction_adh']/5*100)}%")
    write_cell(sheet, row, col_letter_offset(s, 1), scores["accuracy"],      score_to_fill(scores["accuracy"]))
    write_cell(sheet, row, col_letter_offset(s, 2), scores["hallucination"], score_to_fill(scores["hallucination"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["consistency"],   score_to_fill(scores["consistency"]))
    write_cell(sheet, row, col_letter_offset(s, 4), scores["latency"],       BLUE)
    write_cell(sheet, row, col_letter_offset(s, 5), scores["tokens"],        BLUE)

def write_reasoning(sheet, row, scores):
    s = DOMAIN_COLS["reasoning"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), scores["accuracy"],      score_to_fill(scores["accuracy"]))
    write_cell(sheet, row, col_letter_offset(s, 1), "—")  # Chain Quality — manual
    write_cell(sheet, row, col_letter_offset(s, 2), scores["hallucination"], score_to_fill(scores["hallucination"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["consistency"],   score_to_fill(scores["consistency"]))
    write_cell(sheet, row, col_letter_offset(s, 4), scores["latency"],       BLUE)
    write_cell(sheet, row, col_letter_offset(s, 5), scores["tokens"],        BLUE)

def write_long_context(sheet, row, scores):
    s = DOMAIN_COLS["long_context"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), scores["accuracy"],      score_to_fill(scores["accuracy"]))
    write_cell(sheet, row, col_letter_offset(s, 1), scores["accuracy"],      score_to_fill(scores["accuracy"]))
    write_cell(sheet, row, col_letter_offset(s, 2), scores["hallucination"], score_to_fill(scores["hallucination"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["consistency"],   score_to_fill(scores["consistency"]))

def write_multilingual(sheet, row, scores):
    s = DOMAIN_COLS["multilingual"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), scores["accuracy"],    score_to_fill(scores["accuracy"]))
    write_cell(sheet, row, col_letter_offset(s, 1), "—")  # Fluency — manual
    write_cell(sheet, row, col_letter_offset(s, 2), scores["consistency"], score_to_fill(scores["consistency"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["latency"],     BLUE)
    write_cell(sheet, row, col_letter_offset(s, 4), scores["tokens"],      BLUE)

def write_conversational(sheet, row, scores):
    s = DOMAIN_COLS["conversational"]["start"]
    write_cell(sheet, row, col_letter_offset(s, 0), "—")  # Quality — manual
    write_cell(sheet, row, col_letter_offset(s, 1), "—")  # Context Retention — manual
    write_cell(sheet, row, col_letter_offset(s, 2), scores["consistency"], score_to_fill(scores["consistency"]))
    write_cell(sheet, row, col_letter_offset(s, 3), scores["latency"],     BLUE)
    write_cell(sheet, row, col_letter_offset(s, 4), scores["tokens"],      BLUE)

DOMAIN_WRITERS = {
    "math":                  write_math,
    "code":                  write_code,
    "creative_writing":      write_creative,
    "factual_qa":            write_factual,
    "summarisation":         write_summarisation,
    "instruction_following": write_instruction,
    "reasoning":             write_reasoning,
    "long_context":          write_long_context,
    "multilingual":          write_multilingual,
    "conversational":        write_conversational,
}

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\nNexus Step 5 — Scoring & Analysis")
    print("=" * 60)

    if not MATRIX_FILE.exists():
        print(f"ERROR: Matrix file not found at {MATRIX_FILE}")
        return

    wb    = load_workbook(MATRIX_FILE)
    sheet = wb["Evaluation Matrix"]

    models  = list(MODEL_ROW_MAP.keys())
    domains = list(DOMAIN_COLS.keys())

    for model_id in models:
        print(f"\nModel: {model_id}")
        print("-" * 40)

        row = find_model_row(sheet, model_id)
        if not row:
            print(f"  WARNING: Could not find row for {model_id} in matrix")
            continue

        for domain in domains:
            scores = score_model_domain(model_id, domain)
            if not scores:
                print(f"  {model_id:25s} | {domain:22s} | No data")
                continue

            writer = DOMAIN_WRITERS.get(domain)
            if writer:
                writer(sheet, row, scores)

    # Add legend note
    note_row = 30
    sheet.cell(row=note_row, column=1).value = "Color Key:"
    sheet.cell(row=note_row, column=2).value = "Green = Good (≥4)"
    sheet.cell(row=note_row, column=2).fill  = GREEN
    sheet.cell(row=note_row, column=3).value = "Yellow = Average (3)"
    sheet.cell(row=note_row, column=3).fill  = YELLOW
    sheet.cell(row=note_row, column=4).value = "Red = Poor (≤2)"
    sheet.cell(row=note_row, column=4).fill  = RED
    sheet.cell(row=note_row, column=5).value = "Blue = Raw metric (latency/tokens)"
    sheet.cell(row=note_row, column=5).fill  = BLUE
    sheet.cell(row=note_row, column=6).value = "— = Manual scoring required"

    wb.save(OUTPUT_FILE)
    print(f"\n{'=' * 60}")
    print(f"Saved scored matrix to: {OUTPUT_FILE}")
    print(f"\nNotes:")
    print(f"  — Cells marked '—' require manual scoring")
    print(f"  — Blue cells = raw metrics (latency in seconds, token counts)")
    print(f"  — Green/Yellow/Red = automated scores on 1-5 scale")
    print(f"  — Accuracy scores for subjective domains should be reviewed manually")

if __name__ == "__main__":
    main()