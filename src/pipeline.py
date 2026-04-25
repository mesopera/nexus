"""
Nexus Evaluation Pipeline
==========================
Automated testing pipeline for running benchmark prompts against models.
Phase 1 implementation: Ollama (local) models.
API providers (Groq, Together AI, Mistral, Google, Cohere) added in Task 22.

Usage:
    # Run a single model against a single domain
    python src/pipeline.py --model llama3.1:8b --domain math

    # Run a single model against all domains
    python src/pipeline.py --model llama3.1:8b --domain all

    # Run all configured models against all domains
    python src/pipeline.py --all

    # Run adversarial prompts only
    python src/pipeline.py --model llama3.1:8b --domain math --adversarial

    # Dry run (prints config without executing)
    python src/pipeline.py --model llama3.1:8b --domain math --dry-run

Output:
    /workspaces/nexus/data/results/<model_id>/<domain>/results.json
    /workspaces/nexus/data/results/<model_id>/<domain>/adversarial_results.json

Result schema per prompt:
    {
        "run":              int,        # 1, 2, or 3
        "prompt_id":        str,        # domain_source_index
        "domain":           str,
        "difficulty":       str,
        "prompt":           str,
        "expected_answer":  str,
        "response":         str,
        "latency_s":        float,      # seconds
        "prompt_tokens":    int,
        "response_tokens":  int,
        "total_tokens":     int,
        "model":            str,
        "provider":         str,
        "timestamp":        str,        # ISO 8601
        "error":            str|null    # null if successful
    }
"""

import json
import time
import argparse
import requests
import os
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).resolve().parent.parent
BENCH_DIR   = BASE_DIR / "data" / "benchmarks"
RESULTS_DIR = BASE_DIR / "data" / "results"

# ── Model Registry ────────────────────────────────────────────────────────────
# Each entry defines a model+provider combination.
# provider_type determines which connector is used.
# rate_limit_s is the minimum delay between requests for this provider.

MODELS = {
    # Ollama local models
    "llama3.1:8b": {
        "display_name":    "LLaMA 3.1 8B",
        "provider":        "Ollama (Local)",
        "provider_type":   "ollama",
        "ollama_tag":      "llama3.1:8b",
        "rate_limit_s":    0.5,
    },
    "llama3.1:70b": {
        "display_name":    "LLaMA 3.1 70B",
        "provider":        "Ollama (Local)",
        "provider_type":   "ollama",
        "ollama_tag":      "llama3.1:70b",
        "rate_limit_s":    1.0,
    },
    "mistral:7b": {
        "display_name":    "Mistral 7B",
        "provider":        "Ollama (Local)",
        "provider_type":   "ollama",
        "ollama_tag":      "mistral:7b",
        "rate_limit_s":    0.5,
    },
    "mixtral:8x7b": {
        "display_name":    "Mixtral 8x7B",
        "provider":        "Ollama (Local)",
        "provider_type":   "ollama",
        "ollama_tag":      "mixtral:8x7b",
        "rate_limit_s":    1.0,
    },
    "phi3:medium": {
        "display_name":    "Phi-3 Medium",
        "provider":        "Ollama (Local)",
        "provider_type":   "ollama",
        "ollama_tag":      "phi3:medium",
        "rate_limit_s":    0.5,
    },
    "gemma2:9b": {
        "display_name":    "Gemma 2 9B",
        "provider":        "Ollama (Local)",
        "provider_type":   "ollama",
        "ollama_tag":      "gemma2:9b",
        "rate_limit_s":    0.5,
    },
    "gemma2:27b": {
        "display_name":    "Gemma 2 27B",
        "provider":        "Ollama (Local)",
        "provider_type":   "ollama",
        "ollama_tag":      "gemma2:27b",
        "rate_limit_s":    1.0,
    },
    "qwen2.5:7b": {
        "display_name":    "Qwen 2.5 7B",
        "provider":        "Ollama (Local)",
        "provider_type":   "ollama",
        "ollama_tag":      "qwen2.5:7b",
        "rate_limit_s":    0.5,
    },
    "qwen2.5:72b": {
        "display_name":    "Qwen 2.5 72B",
        "provider":        "Ollama (Local)",
        "provider_type":   "ollama",
        "ollama_tag":      "qwen2.5:72b",
        "rate_limit_s":    1.0,
    },

    # API models — keys loaded from environment variables
    # These are stubs for now — connectors built in Task 22
    "gemini-1.5-flash": {
        "display_name":    "Gemini 2.5 Flash",
        "provider":        "Google AI Studio",
        "provider_type":   "google",
        "api_model_id":    "gemini-2.5-flash",
        "env_key":         "GOOGLE_API_KEY",
        "rate_limit_s":    10.0,
    },
    "gemini-2.0-flash": {
        "display_name":    "Gemini 2.5 Flash",
        "provider":        "Google AI Studio",
        "provider_type":   "google",
        "api_model_id":    "gemini-2.5-flash",
        "env_key":         "GOOGLE_API_KEY",
        "rate_limit_s":    10.0,
    },
    "llama3.1-70b-groq": {
        "display_name":    "LLaMA 3.1 70B",
        "provider":        "Groq API",
        "provider_type":   "groq",
        "api_model_id":    "llama-3.3-70b-versatile",
        "env_key":         "GROQ_API_KEY",
        "rate_limit_s":    3.0,
    },
    "llama3.1-8b-groq": {
        "display_name":    "LLaMA 3.1 8B",
        "provider":        "Groq API",
        "provider_type":   "groq",
        "api_model_id":    "llama-3.1-8b-instant",
        "env_key":         "GROQ_API_KEY",
        "rate_limit_s":    2.0,
    },
    "gemma2-groq": {
    "display_name":  "Llama 4 Scout 17B",
    "provider":      "Groq API",
    "provider_type": "groq",
    "api_model_id":  "meta-llama/llama-4-scout-17b-16e-instruct",
    "env_key":       "GROQ_API_KEY",
    "rate_limit_s":  10.0,
    },
    "mixtral-groq": {
        "display_name":  "Qwen3 32B",
        "provider":      "Groq API",
        "provider_type": "groq",
        "api_model_id":  "qwen/qwen3-32b",
        "env_key":       "GROQ_API_KEY",
        "rate_limit_s":  2.0,
    },
    "llama3.1-together": {
        "display_name":    "LLaMA 3.1 70B",
        "provider":        "Together AI",
        "provider_type":   "together",
        "api_model_id":    "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "env_key":         "TOGETHER_API_KEY",
        "rate_limit_s":    2.0,
    },
    "qwen2.5-together": {
        "display_name":    "Qwen 2.5 72B",
        "provider":        "Together AI",
        "provider_type":   "together",
        "api_model_id":    "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "env_key":         "TOGETHER_API_KEY",
        "rate_limit_s":    2.0,
    },
    "mistral-api": {
        "display_name":    "Mistral Large",
        "provider":        "Mistral API",
        "provider_type":   "mistral",
        "api_model_id":    "mistral-large-latest",
        "env_key":         "MISTRAL_API_KEY",
        "rate_limit_s":    3.0,
    },
    "mistral-7b-together": {
        "display_name":    "Mistral 7B",
        "provider":        "Together AI",
        "provider_type":   "together",
        "api_model_id":    "mistralai/Mistral-7B-Instruct-v0.3",
        "env_key":         "TOGETHER_API_KEY",
        "rate_limit_s":    2.0,
    },
    "command-r-cohere": {
        "display_name":    "Command R",
        "provider":        "Cohere API",
        "provider_type":   "cohere",
        "api_model_id":    "command-r",
        "env_key":         "COHERE_API_KEY",
        "rate_limit_s":    3.0,
    },
    "phi3-hf": {
        "display_name":    "Phi-3 Medium",
        "provider":        "HuggingFace API",
        "provider_type":   "huggingface",
        "api_model_id":    "microsoft/Phi-3-medium-4k-instruct",
        "env_key":         "HF_TOKEN",
        "rate_limit_s":    3.0,
    },
    "gemma2-27b-hf": {
        "display_name":    "Gemma 2 27B",
        "provider":        "HuggingFace API",
        "provider_type":   "huggingface",
        "api_model_id":    "google/gemma-2-27b-it",
        "env_key":         "HF_TOKEN",
        "rate_limit_s":    3.0,
    },
}

DOMAINS = [
    "math",
    "code",
    "factual_qa",
    "reasoning",
    "instruction_following",
    "summarisation",
    "long_context",
    "multilingual",
    "creative_writing",
    "conversational",
]

OLLAMA_LOCAL_MODELS = [k for k, v in MODELS.items() if v["provider_type"] == "ollama"]

# ── Connectors ────────────────────────────────────────────────────────────────

def query_ollama(prompt: str, model_config: dict) -> dict:
    """Send a prompt to a local Ollama model and return response data."""
    url  = "http://localhost:11434/api/generate"
    tag  = model_config["ollama_tag"]

    payload = {
        "model":  tag,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 2048,
        }
    }

    start = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        latency = round(time.time() - start, 3)
        data    = resp.json()

        return {
            "response":        data.get("response", "").strip(),
            "latency_s":       latency,
            "prompt_tokens":   data.get("prompt_eval_count", 0),
            "response_tokens": data.get("eval_count", 0),
            "total_tokens":    data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            "error":           None,
        }
    except requests.exceptions.ConnectionError:
        return {
            "response": "", "latency_s": 0,
            "prompt_tokens": 0, "response_tokens": 0, "total_tokens": 0,
            "error": "Ollama not running. Start with: ollama serve"
        }
    except Exception as e:
        return {
            "response": "", "latency_s": round(time.time() - start, 3),
            "prompt_tokens": 0, "response_tokens": 0, "total_tokens": 0,
            "error": str(e)
        }

def query_api(prompt: str, model_config: dict) -> dict:
    """Connectors for Groq, Together AI, Google, Mistral, Cohere, HuggingFace."""
    provider = model_config["provider_type"]
    env_key  = model_config.get("env_key", "")
    api_key  = os.environ.get(env_key, "")

    if not api_key:
        return {
            "response": "", "latency_s": 0,
            "prompt_tokens": 0, "response_tokens": 0, "total_tokens": 0,
            "error": f"Missing environment variable: {env_key}"
        }

    start = time.time()

    try:
        # ── Groq ──────────────────────────────────────────────────────────
        if provider == "groq":
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model_config["api_model_id"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.7,
                },
                timeout=60
            )
            resp.raise_for_status()
            data    = resp.json()
            latency = round(time.time() - start, 3)
            choice  = data["choices"][0]["message"]["content"].strip()
            usage   = data.get("usage", {})
            return {
                "response":        choice,
                "latency_s":       latency,
                "prompt_tokens":   usage.get("prompt_tokens", 0),
                "response_tokens": usage.get("completion_tokens", 0),
                "total_tokens":    usage.get("total_tokens", 0),
                "error":           None,
            }

        # ── Together AI ───────────────────────────────────────────────────
        elif provider == "together":
            resp = requests.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model_config["api_model_id"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.7,
                },
                timeout=60
            )
            resp.raise_for_status()
            data    = resp.json()
            latency = round(time.time() - start, 3)
            choice  = data["choices"][0]["message"]["content"].strip()
            usage   = data.get("usage", {})
            return {
                "response":        choice,
                "latency_s":       latency,
                "prompt_tokens":   usage.get("prompt_tokens", 0),
                "response_tokens": usage.get("completion_tokens", 0),
                "total_tokens":    usage.get("total_tokens", 0),
                "error":           None,
            }

        # ── Google (Gemini) ───────────────────────────────────────────────
        elif provider == "google":
            model_id = model_config["api_model_id"]
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.7},
                },
                timeout=60
            )
            resp.raise_for_status()
            data      = resp.json()
            latency   = round(time.time() - start, 3)
            text      = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            usage     = data.get("usageMetadata", {})
            return {
                "response":        text,
                "latency_s":       latency,
                "prompt_tokens":   usage.get("promptTokenCount", 0),
                "response_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens":    usage.get("totalTokenCount", 0),
                "error":           None,
            }

        # ── Mistral ───────────────────────────────────────────────────────
        elif provider == "mistral":
            resp = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model_config["api_model_id"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.7,
                },
                timeout=60
            )
            resp.raise_for_status()
            data    = resp.json()
            latency = round(time.time() - start, 3)
            choice  = data["choices"][0]["message"]["content"].strip()
            usage   = data.get("usage", {})
            return {
                "response":        choice,
                "latency_s":       latency,
                "prompt_tokens":   usage.get("prompt_tokens", 0),
                "response_tokens": usage.get("completion_tokens", 0),
                "total_tokens":    usage.get("total_tokens", 0),
                "error":           None,
            }

        # ── Cohere ────────────────────────────────────────────────────────
        elif provider == "cohere":
            resp = requests.post(
                "https://api.cohere.com/v2/chat",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model_config["api_model_id"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.7,
                },
                timeout=60
            )
            resp.raise_for_status()
            data    = resp.json()
            latency = round(time.time() - start, 3)
            text    = data["message"]["content"][0]["text"].strip()
            usage   = data.get("usage", {}).get("tokens", {})
            return {
                "response":        text,
                "latency_s":       latency,
                "prompt_tokens":   usage.get("input_tokens", 0),
                "response_tokens": usage.get("output_tokens", 0),
                "total_tokens":    usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                "error":           None,
            }

        # ── HuggingFace ───────────────────────────────────────────────────
        elif provider == "huggingface":
            model_id = model_config["api_model_id"]
            resp = requests.post(
                f"https://api-inference.huggingface.co/models/{model_id}/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.7,
                },
                timeout=120
            )
            resp.raise_for_status()
            data    = resp.json()
            latency = round(time.time() - start, 3)
            choice  = data["choices"][0]["message"]["content"].strip()
            usage   = data.get("usage", {})
            return {
                "response":        choice,
                "latency_s":       latency,
                "prompt_tokens":   usage.get("prompt_tokens", 0),
                "response_tokens": usage.get("completion_tokens", 0),
                "total_tokens":    usage.get("total_tokens", 0),
                "error":           None,
            }

        else:
            return {
                "response": "", "latency_s": 0,
                "prompt_tokens": 0, "response_tokens": 0, "total_tokens": 0,
                "error": f"Unknown provider type: {provider}"
            }

    except requests.exceptions.HTTPError as e:
        return {
            "response": "", "latency_s": round(time.time() - start, 3),
            "prompt_tokens": 0, "response_tokens": 0, "total_tokens": 0,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        }
    except Exception as e:
        return {
            "response": "", "latency_s": round(time.time() - start, 3),
            "prompt_tokens": 0, "response_tokens": 0, "total_tokens": 0,
            "error": str(e)
        }


def query_model(prompt: str, model_config: dict) -> dict:
    """Route to the correct connector based on provider_type."""
    if model_config["provider_type"] == "ollama":
        return query_ollama(prompt, model_config)
    else:
        return query_api(prompt, model_config)


# ── Prompt ID generator ───────────────────────────────────────────────────────

def make_prompt_id(domain: str, prompt: dict, index: int) -> str:
    source = prompt.get("source", "custom").replace("/", "_").replace(" ", "_")
    diff   = prompt.get("difficulty", "unknown")
    cat    = prompt.get("category", "")
    if cat:
        return f"{domain}_{source}_{cat}_{index:04d}"
    return f"{domain}_{source}_{diff}_{index:04d}"


# ── Core runner ───────────────────────────────────────────────────────────────

def run_domain(model_id: str, domain: str, adversarial: bool = False,
               dry_run: bool = False) -> list:
    """
    Run all prompts for a domain against a model.
    Returns list of result dicts.
    """
    model_config = MODELS[model_id]
    fname        = "adversarial.json" if adversarial else "prompts.json"
    prompt_file  = BENCH_DIR / domain / fname

    if not prompt_file.exists():
        print(f"  [SKIP] {prompt_file} not found")
        return []

    with open(prompt_file,encoding="utf-8") as f:
        prompts = json.load(f)

    tag         = "adversarial" if adversarial else "standard"
    model_label = f"{model_config['display_name']} ({model_config['provider']})"
    print(f"\n  Model   : {model_label}")
    print(f"  Domain  : {domain}")
    print(f"  Type    : {tag}")
    print(f"  Prompts : {len(prompts)} x 3 runs = {len(prompts) * 3} total queries")

    if dry_run:
        print("  [DRY RUN] No queries will be sent.")
        return []

    results       = []
    rate_limit    = model_config.get("rate_limit_s", 1.0)
    total_queries = len(prompts) * 3
    query_count   = 0

    for idx, prompt_data in enumerate(prompts):
        prompt_id   = make_prompt_id(domain, prompt_data, idx)
        prompt_text = prompt_data["prompt"]

        for run_num in range(1, 4):
            query_count += 1
            print(f"  [{query_count:>4}/{total_queries}] prompt {idx+1:>3}  run {run_num}/3  ... ",
                  end="", flush=True)

            result_data = query_model(prompt_text, model_config)

            result = {
                "run":             run_num,
                "prompt_id":       prompt_id,
                "domain":          domain,
                "difficulty":      prompt_data.get("difficulty", ""),
                "category":        prompt_data.get("category", ""),
                "prompt":          prompt_text,
                "expected_answer": prompt_data.get("expected_answer", ""),
                "response":        result_data["response"],
                "latency_s":       result_data["latency_s"],
                "prompt_tokens":   result_data["prompt_tokens"],
                "response_tokens": result_data["response_tokens"],
                "total_tokens":    result_data["total_tokens"],
                "model_id":        model_id,
                "model_name":      model_config["display_name"],
                "provider":        model_config["provider"],
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "error":           result_data["error"],
            }
            results.append(result)

            if result_data["error"]:
                print(f"ERROR: {result_data['error']}")
            else:
                print(f"{result_data['latency_s']:.2f}s  "
                      f"{result_data['response_tokens']} tokens")

            # Rate limiting between requests
            if query_count < total_queries:
                time.sleep(rate_limit)

    return results


def save_results(model_id: str, domain: str, results: list,
                 adversarial: bool = False):
    """Save results to the structured output path."""
    safe_model_id = model_id.replace(":", "_").replace("/", "_")
    out_dir       = RESULTS_DIR / safe_model_id / domain
    out_dir.mkdir(parents=True, exist_ok=True)

    fname    = "adversarial_results.json" if adversarial else "results.json"
    out_file = out_dir / fname

    # If file exists, load and merge (append new runs)
    if out_file.exists():
        with open(out_file) as f:
            existing = json.load(f)
        existing.extend(results)
        results = existing

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    errors = sum(1 for r in results if r.get("error"))
    print(f"  Saved {len(results)} results -> {out_file}")
    if errors:
        print(f"  Warning: {errors} errors recorded in results")


def print_summary(model_id: str, domain: str, results: list):
    """Print a quick summary after a run completes."""
    if not results:
        return
    successful  = [r for r in results if not r.get("error")]
    errors      = [r for r in results if r.get("error")]
    avg_latency = (sum(r["latency_s"] for r in successful) / len(successful)
                   if successful else 0)
    avg_tokens  = (sum(r["response_tokens"] for r in successful) / len(successful)
                   if successful else 0)

    print(f"\n  Run summary:")
    print(f"    Total results : {len(results)}")
    print(f"    Successful    : {len(successful)}")
    print(f"    Errors        : {len(errors)}")
    print(f"    Avg latency   : {avg_latency:.2f}s")
    print(f"    Avg tokens    : {avg_tokens:.0f}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Nexus Evaluation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/pipeline.py --model llama3.1:8b --domain math
  python src/pipeline.py --model llama3.1:8b --domain all
  python src/pipeline.py --model llama3.1:8b --domain math --adversarial
  python src/pipeline.py --all
  python src/pipeline.py --model llama3.1:8b --domain math --dry-run
  python src/pipeline.py --list-models
        """
    )

    parser.add_argument("--model",       type=str, help="Model ID from registry (e.g. llama3.1:8b)")
    parser.add_argument("--domain",      type=str, help="Domain name or 'all'")
    parser.add_argument("--adversarial", action="store_true", help="Run adversarial prompts instead of standard")
    parser.add_argument("--dry-run",     action="store_true", help="Print config without running")
    parser.add_argument("--all",         action="store_true", help="Run all Ollama models against all domains")
    parser.add_argument("--list-models", action="store_true", help="List all available model IDs")
    args = parser.parse_args()

    if args.list_models:
        print("\nAvailable models:\n")
        for model_id, cfg in MODELS.items():
            status = "(ready)" if cfg["provider_type"] == "ollama" else "(Task 22)"
            print(f"  {model_id:30s}  {cfg['display_name']:20s}  {cfg['provider']:20s}  {status}")
        return

    if args.all:
        print("\nRunning all Ollama models against all domains")
        print("=" * 60)
        for model_id in OLLAMA_LOCAL_MODELS:
            for domain in DOMAINS:
                results = run_domain(model_id, domain,
                                     adversarial=args.adversarial,
                                     dry_run=args.dry_run)
                if results:
                    save_results(model_id, domain, results, args.adversarial)
                    print_summary(model_id, domain, results)
        return

    if not args.model:
        parser.error("--model is required unless using --all or --list-models")
    if not args.domain:
        parser.error("--domain is required unless using --all or --list-models")
    if args.model not in MODELS:
        print(f"\nUnknown model '{args.model}'. Run with --list-models to see options.")
        return

    domains = DOMAINS if args.domain == "all" else [args.domain]

    if args.domain != "all" and args.domain not in DOMAINS:
        print(f"\nUnknown domain '{args.domain}'. Available: {', '.join(DOMAINS)}")
        return

    print("\nNexus Evaluation Pipeline")
    print("=" * 60)

    for domain in domains:
        results = run_domain(args.model, domain,
                             adversarial=args.adversarial,
                             dry_run=args.dry_run)
        if results:
            save_results(args.model, domain, results, args.adversarial)
            print_summary(args.model, domain, results)

    print("\nDone.")


if __name__ == "__main__":
    main()