"""Explicit paid evaluation: python -m app.evaluate --limit 10 --routing-only."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .agents import build_graph
from .prompts import ROUTER
from .provider import Provider
from .schemas import Route


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--routing-only", action="store_true")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    cases = json.loads(Path("evals/cases.json").read_text(encoding="utf-8"))[: max(1, args.limit)]
    provider = Provider()
    all_runs = []
    for run in range(max(1, args.runs)):
        results = []
        for case in cases:
            try:
                if args.routing_only:
                    route = provider.structured(ROUTER, case["message"], Route).route
                    item = {**case, "actual_route": route, "pass": route == case["route"]}
                else:
                    result = build_graph(provider).invoke(
                        {"message": case["message"], "user_id": "cliente1988", "steps": []}
                    )
                    item = {
                        **case,
                        "actual_route": result["route"].route,
                        "pass": result["route"].route == case["route"],
                        "answer": result["answer"],
                        "status": result["status"],
                        "sources": result.get("sources", []),
                    }
                results.append(item)
                print(
                    json.dumps(
                        {
                            "run": run + 1,
                            "case": len(results),
                            "pass": item["pass"],
                            "route": item["actual_route"],
                        }
                    ),
                    flush=True,
                )
            except Exception as exc:
                results.append({**case, "pass": False, "error_type": type(exc).__name__})
        all_runs.append(results)
    results = all_runs[-1]
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "routing" if args.routing_only else "end_to_end",
        "route_accuracy": sum(x["pass"] for x in results) / len(results),
        "runs": [{"route_accuracy": sum(x["pass"] for x in run) / len(run)} for run in all_runs],
        "results": results,
    }
    target = Path("data/reports")
    target.mkdir(parents=True, exist_ok=True)
    (target / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    factual = [item for item in results if item.get("route") in {"knowledge", "knowledge_support"}]
    grounded = [item for item in factual if item.get("sources")]
    citation_coverage = (
        "não medido em modo routing-only"
        if args.routing_only
        else f"{(len(grounded) / len(factual) if factual else 1):.1%}"
    )
    lines = [
        "# Relatório de avaliação",
        "",
        f"- Execuções: {len(all_runs)}",
        f"- Acerto de rota: {report['route_accuracy']:.1%}",
        f"- Cobertura de citações em respostas de conhecimento: {citation_coverage}",
        "- Correção factual e groundedness exigem revisão da resposta contra as fontes; a presença de citações não é prova disso.",
        "- Recusas corretas, falsos positivos, handoff, latência p50/p95, tokens e custo exigem análise própria dos resultados end-to-end.",
    ]
    Path("evals/report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Routing accuracy:", report["route_accuracy"])


if __name__ == "__main__":
    main()
