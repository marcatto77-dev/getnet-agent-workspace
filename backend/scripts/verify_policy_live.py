"""Paid checks of current routing, consent classification, multilingual RAG and FX.

Run from repository root with PYTHONPATH=backend and configured OpenAI/database.
No handoff is created by these scenarios. Answers are printed for source review.
"""

import argparse
import json
import re
from pathlib import Path

from app.agents import build_graph
from app.guardrails.input import inspect_input
from app.prompts import ROUTER
from app.provider import Provider
from app.schemas import Route


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers-only", action="store_true")
    args = parser.parse_args()
    provider = Provider()
    failures = []
    cases = json.loads(Path("evals/cases.json").read_text(encoding="utf-8"))[:10]
    for index, case in enumerate([] if args.answers_only else cases, 1):
        route = provider.structured(
            ROUTER, json.dumps({"message": case["message"], "conversation_memory": {}}), Route
        )
        passed = route.route == case["route"]
        if not passed:
            failures.append(f"routing-{index}")
        print(
            json.dumps({"case": index, "expected": case["route"], "actual": route.route, "pass": passed}),
            flush=True,
        )

    consent_cases = [
        (
            "Isso ainda não resolveu meu problema com a Getnet",
            {"assistance_count": 3},
            "customer_dissatisfied",
            True,
        ),
        ("Sim, por favor", {"assistance_count": 3, "handoff_offered": True}, "accepts_human_offer", True),
        (
            "Não, prefiro continuar por aqui",
            {"assistance_count": 3, "handoff_offered": True},
            "accepts_human_offer",
            False,
        ),
    ]
    for message, memory, field, expected in [] if args.answers_only else consent_cases:
        route = provider.structured(
            ROUTER, json.dumps({"message": message, "conversation_memory": memory}, ensure_ascii=False), Route
        )
        passed = getattr(route, field) is expected
        if not passed:
            failures.append(field + ":" + message)
        print(
            json.dumps({"consent": message, "field": field, "pass": passed}, ensure_ascii=False), flush=True
        )

    for message, language in [
        ("What is Getnet Payment Link used for?", "en"),
        ("¿Para qué sirve el Link de Pago de Getnet?", "es"),
        ("What's the EUR/BRL exchange rate today?", "en"),
    ]:
        decision = inspect_input(message, "cliente1988", "getnet_exchange")
        assert not decision.block
        result = build_graph(provider).invoke(
            {"message": message, "user_id": "cliente1988", "steps": [], "conversation_memory": {}}
        )
        passed = result["route"].route == "knowledge" and result["status"] in {"ok", "needs_clarification"}
        passed = passed and result["route"].language == language
        if "exchange rate" not in message:
            markers = (
                r"\b(?:is|allows|used|can|customers|businesses)\b"
                if language == "en"
                else r"\b(?:enlace|pagos|compartir|sirve)\b"
            )
            passed = (
                passed
                and result["status"] == "ok"
                and bool(result.get("sources"))
                and bool(re.search(markers, result["answer"], re.I))
            )
        if not passed:
            failures.append(message)
        sources = [
            {key: source.get(key) for key in ("title", "url", "kind")} for source in result.get("sources", [])
        ]
        print(
            json.dumps(
                {
                    "message": message,
                    "route": result["route"].route,
                    "language": result["route"].language,
                    "status": result["status"],
                    "answer": result["answer"],
                    "sources": sources,
                    "pass": passed,
                },
                ensure_ascii=False,
                default=str,
            ),
            flush=True,
        )
    if failures:
        raise SystemExit("Failures: " + ", ".join(failures))
    print("Live policy checks passed; inspect answers and sources for factual quality.", flush=True)


if __name__ == "__main__":
    main()
