#!/usr/bin/env python3
"""hibrid local-tier benchmark — runs ON a machine, times its local models on a fixed
real-task suite via the ollama OpenAI-compatible endpoint. Stdlib only.

Emits JSON to stdout: machine profile + per (model,task) latency, tokens, tok/s, output.
The strong-tier reference answers and quality judging are done separately by the
orchestration layer (no API key), so this script makes ZERO paid calls.

Usage:  python3 bench.py [endpoint]   (default http://localhost:11434/v1)
"""
import json, os, platform, subprocess, sys, time, urllib.request

ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:11434/v1"

# Fixed suite of real use-cases, tagged with the hibrid task_type/axis they exercise.
TASKS = [
    {"id": "translate", "task_type": "simple", "axis": "general",
     "prompt": "Translate to English, output only the translation:\n"
               "'El gato se sentó en la alfombra y observó la lluvia por la ventana.'"},
    {"id": "classify", "task_type": "simple", "axis": "general",
     "prompt": "Classify the sentiment as POSITIVE, NEGATIVE or NEUTRAL. Output one word.\n"
               "Review: 'The build is fast but the docs are confusing and support never replied.'"},
    {"id": "extract", "task_type": "simple", "axis": "general",
     "prompt": "Extract the emails as a JSON array, nothing else:\n"
               "'Contact ana@acme.io or, for billing, finance@acme.io (not sales@old.example).'"},
    {"id": "summarize", "task_type": "general", "axis": "general",
     "prompt": "Summarize in exactly one sentence:\n"
               "'Edge routing sends each request to the cheapest model that can handle it. "
               "Small models run locally; only hard steps escalate. This cuts cost and keeps "
               "private data on the machine, at the price of a routing decision per call.'"},
    {"id": "code_fix", "task_type": "loop_refine", "axis": "code",
     "prompt": "This Python function should return the factorial but has a bug. "
               "Return only the corrected function:\n"
               "def fact(n):\n    r = 0\n    for i in range(1, n+1):\n        r *= i\n    return r"},
    {"id": "code_write", "task_type": "general", "axis": "code",
     "prompt": "Write a Python function is_palindrome(s) that ignores case and non-alphanumeric "
               "characters. Return only the code."},
    {"id": "reason", "task_type": "deep_reason", "axis": "reasoning",
     "prompt": "A bat and a ball cost 1.10 in total. The bat costs 1.00 more than the ball. "
               "How much does the ball cost? Show the steps briefly and give the final number."},
]


def list_models():
    try:
        out = subprocess.check_output(["ollama", "list"], text=True, timeout=20)
        models = []
        for line in out.splitlines()[1:]:
            if line.strip():
                models.append(line.split()[0])
        return models
    except Exception as e:
        print(f"# could not list models: {e}", file=sys.stderr)
        return []


def machine_profile():
    ram_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
    cpu = platform.processor() or platform.machine()
    try:
        for ln in open("/proc/cpuinfo"):
            if ln.startswith("model name"):
                cpu = ln.split(":", 1)[1].strip(); break
    except Exception:
        pass
    return {"host": platform.node(), "os": platform.system(), "arch": platform.machine(),
            "cpu": cpu, "cores": os.cpu_count(), "ram_gb": ram_gb}


def call(model, prompt, max_tokens=256):
    body = json.dumps({"model": model, "temperature": 0.0, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{ENDPOINT}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read())
    dt = time.perf_counter() - t0
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    ct = usage.get("completion_tokens") or max(1, len(text) // 4)
    return {"latency_s": round(dt, 2), "completion_tokens": ct,
            "tok_s": round(ct / dt, 1) if dt > 0 else 0.0, "output": text.strip()}


def main():
    models = list_models()
    prof = machine_profile()
    results = []
    # warm-up (load weights) so the first task isn't penalised by model load time
    for m in models:
        try:
            call(m, "ok", max_tokens=1)
        except Exception as e:
            print(f"# warmup fail {m}: {e}", file=sys.stderr)
    for m in models:
        for task in TASKS:
            try:
                r = call(m, task["prompt"])
                r.update({"model": m, "task": task["id"], "task_type": task["task_type"],
                          "axis": task["axis"]})
                results.append(r)
                print(f"# {m} {task['id']}: {r['tok_s']} tok/s, {r['latency_s']}s",
                      file=sys.stderr)
            except Exception as e:
                print(f"# FAIL {m} {task['id']}: {e}", file=sys.stderr)
                results.append({"model": m, "task": task["id"], "error": str(e)})
    print(json.dumps({"machine": prof, "endpoint": ENDPOINT, "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
