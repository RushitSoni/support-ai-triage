"""
eval.py — Offline evaluation for the ticket classification prompt.

Runs every ticket in eval_set.jsonl through the same classification prompt
and JSON schema used in the n8n "Classify Ticket" node, then compares the
model's output against your hand-labeled gold answers.

Usage:
    export GROQ_API_KEY=your_key_here
    pip install requests --break-system-packages   # if not already installed
    python3 eval.py

Tracks (per Section 10.1 of the roadmap):
  - category accuracy
  - urgency accuracy
  - risk_flag accuracy, and specifically the FALSE NEGATIVE rate on risk_flag
    (gold says risky, model said not risky) — this is the single most
    dangerous failure mode, since it's what could let a risky ticket
    auto-resolve.
"""

import json
import os
import sys
import time
import urllib.request

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = (
    "You are a support-ticket triage classifier. Return ONLY a JSON object "
    "matching the schema. confidence reflects how sure you are about the "
    "category AND that an automated reply would be appropriate. risk_flag = "
    "true forces human review regardless of confidence for billing, legal, "
    "security, or angry-customer tickets. Never invent policy details."
)

JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "ticket_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["billing", "bug", "how_to", "account", "feature_request", "other"],
                },
                "intent": {"type": "string"},
                "urgency": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative", "angry"]},
                "confidence": {"type": "number"},
                "risk_flag": {"type": "boolean"},
                "pii_present": {"type": "boolean"},
                "reasoning": {"type": "string"},
            },
            "required": [
                "category", "intent", "urgency", "sentiment",
                "confidence", "risk_flag", "pii_present", "reasoning",
            ],
            "additionalProperties": False,
        },
    },
}


def classify(subject: str, body_raw: str) -> dict:
    """Call Groq's API and return the parsed classification dict."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Subject: {subject}\nBody: {body_raw}"},
        ],
        "response_format": JSON_SCHEMA,
    }
    req = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            # Groq's API sits behind Cloudflare, which blocks the default
            # Python-urllib User-Agent with a 403 (Cloudflare error 1010).
            # Setting a normal-looking User-Agent avoids that block.
            "User-Agent": "Mozilla/5.0 (compatible; support-ai-triage-eval/1.0)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    raw = data["choices"][0]["message"]["content"]
    parsed = json.loads(raw)
    # Same hard-coded safety override used in the n8n Parse Classification node
    if parsed.get("category") == "billing" or parsed.get("sentiment") == "angry":
        parsed["risk_flag"] = True
    return parsed


def load_eval_set(path: str) -> list[dict]:
    items = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def run_eval(eval_set_path: str) -> None:
    if not GROQ_API_KEY:
        print("ERROR: set GROQ_API_KEY environment variable first.")
        sys.exit(1)

    eval_set = load_eval_set(eval_set_path)
    total = len(eval_set)
    category_correct = 0
    urgency_correct = 0
    risk_correct = 0
    false_negative_risks = []  # gold risky, predicted not risky — the dangerous case
    results = []

    for i, item in enumerate(eval_set, 1):
        print(f"[{i}/{total}] Classifying: {item['subject']!r}")
        try:
            pred = classify(item["subject"], item["body_raw"])
        except Exception as e:
            print(f"  ERROR calling API: {e}")
            continue

        cat_ok = pred.get("category") == item["gold_category"]
        urg_ok = pred.get("urgency") == item["gold_urgency"]
        risk_ok = pred.get("risk_flag") == item["gold_risk_flag"]

        category_correct += cat_ok
        urgency_correct += urg_ok
        risk_correct += risk_ok

        if item["gold_risk_flag"] and not pred.get("risk_flag"):
            false_negative_risks.append(item["subject"])

        results.append({
            "subject": item["subject"],
            "gold_category": item["gold_category"], "pred_category": pred.get("category"),
            "gold_urgency": item["gold_urgency"], "pred_urgency": pred.get("urgency"),
            "gold_risk": item["gold_risk_flag"], "pred_risk": pred.get("risk_flag"),
        })

        time.sleep(0.5)  # be polite to the API / avoid rate limits

    


    print("\n=== EVAL RESULTS ===")
    print(f"Total tickets:      {total}")
    print(f"Category accuracy:  {category_correct}/{total} ({100*category_correct/total:.1f}%)")
    print(f"Urgency accuracy:   {urgency_correct}/{total} ({100*urgency_correct/total:.1f}%)")
    print(f"Risk flag accuracy: {risk_correct}/{total} ({100*risk_correct/total:.1f}%)")
    print(f"DANGEROUS false negatives on risk_flag: {len(false_negative_risks)}")
    if false_negative_risks:
        print("  These risky tickets were NOT flagged for human review:")
        for s in false_negative_risks:
            print(f"   - {s}")

    with open("eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nFull per-ticket results saved to eval_results.json")

    # --- Pass/fail gate -------------------------------------------------
    # These are the thresholds CI enforces. Tune them here, not in the
    # workflow YAML, so the gate logic stays with the eval itself.
    MIN_CATEGORY_ACC = 0.70
    MIN_RISK_ACC = 0.90
    MAX_FALSE_NEGATIVES = 0          # any risky ticket slipping through fails the build

    category_acc = category_correct / total
    risk_acc = risk_correct / total

    failures = []
    if len(false_negative_risks) > MAX_FALSE_NEGATIVES:
        failures.append(
            f"{len(false_negative_risks)} risky ticket(s) NOT flagged "
            f"(max allowed: {MAX_FALSE_NEGATIVES})"
        )
    if category_acc < MIN_CATEGORY_ACC:
        failures.append(f"category accuracy {category_acc:.1%} < required {MIN_CATEGORY_ACC:.0%}")
    if risk_acc < MIN_RISK_ACC:
        failures.append(f"risk_flag accuracy {risk_acc:.1%} < required {MIN_RISK_ACC:.0%}")

    if failures:
        print("\n=== EVAL FAILED ===")
        for f_ in failures:
            print(f"  - {f_}")
        sys.exit(1)

    print("\n=== EVAL PASSED ===")


if __name__ == "__main__":
    run_eval(os.path.join(os.path.dirname(__file__), "eval_set.jsonl"))