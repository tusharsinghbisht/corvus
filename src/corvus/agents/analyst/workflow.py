"""LangGraph single-pass Analyst. No graph checkpoints, retries, tools, or telemetry export.

PostgreSQL owns durable jobs and the no-retry request boundary. This graph executes only
within an already authorized attempt; restarting a graph is never crash recovery.
"""

import json
from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from ...providers import AnalystModel
from ...reporting.evidence import EvidenceCatalog
from ...reporting.schema import REPORT_SCHEMA
from ...reporting.validation import validate_report
from ...storage import parse_json
from ...timeutil import iso
from .prompt import INSTRUCTIONS, PROMPT_VERSION


class AnalystState(TypedDict, total=False):
    bundle: dict
    model: Any
    on_reply: Any
    input_snapshot: Any
    prepared: dict
    messages: list
    started_at: str
    started: float
    reply: Any
    result: dict


def prepare_report(bundle, *, workflow="direct"):
    catalog = EvidenceCatalog(bundle)
    from .planning import PLAN_INSTRUCTIONS, PLAN_SCHEMA, WORKFLOW

    if workflow not in ("direct", "agentic"):
        raise ValueError("Unsupported investigation workflow")
    result = {
        "workflow": deepcopy(WORKFLOW)
        if workflow == "agentic"
        else {"id": "analyst.single_pass.v1", "max_model_requests": 1},
        "prompt_version": PROMPT_VERSION,
        "instructions": INSTRUCTIONS,
        "report_schema": deepcopy(REPORT_SCHEMA),
        "collection_id": catalog.collection_id,
        "evidence_digest": catalog.digest,
        "evidence": catalog.view,
    }
    if workflow == "agentic":
        result.update(plan_schema=deepcopy(PLAN_SCHEMA), plan_instructions=PLAN_INSTRUCTIONS)
    return result


def prepare(state):
    prepared = state.get("input_snapshot") or prepare_report(state["bundle"])
    catalog = EvidenceCatalog(state["bundle"])
    if prepared["evidence_digest"] != catalog.digest or prepared["evidence"] != catalog.view:
        raise ValueError("Prepared input does not match saved selected evidence")
    return {
        "prepared": prepared,
        "messages": [
            {"role": "system", "content": prepared["instructions"]},
            {
                "role": "user",
                "content": json.dumps(
                    {key: value for key, value in prepared.items() if key != "instructions"},
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            },
        ],
        "started_at": iso(datetime.now(timezone.utc)),
        "started": monotonic(),
    }


def request(state):
    reply = state["model"].complete(state["messages"])
    if state.get("on_reply") is not None:
        state["on_reply"](reply)  # Preserve untouched candidate before validation.
    return {"reply": reply}


def validate(state):
    reply = state["reply"]
    raw_output = None
    try:
        report = parse_json(reply.content)
    except ValueError:
        report, raw_output = None, reply.content
    validation = validate_report(report, state["bundle"])
    result = {
        "schema_version": "0.1",
        "analysis_id": str(uuid4()),
        "started_at": state["started_at"],
        "completed_at": iso(datetime.now(timezone.utc)),
        "status": "validated" if validation["valid"] else "rejected",
        "human_review_required": True,
        "prompt_version": state["prepared"]["prompt_version"],
        "evidence_digest": state["prepared"]["evidence_digest"],
        "orchestration": {"framework": "langgraph", "workflow": "analyst.single_pass.v1"},
        "model": {
            "served_model": reply.model,
            "usage": reply.usage,
            "finish_reason": reply.finish_reason,
            "duration_seconds": round(monotonic() - state["started"], 3),
        },
        "report": report,
        "validation": validation,
    }
    if raw_output is not None:
        result["unparseable_output"] = raw_output
    return {"result": result}


def build_graph():
    graph = StateGraph(AnalystState)
    graph.add_node("prepare_input", prepare, retry_policy=None)
    graph.add_node("model_request", request, retry_policy=None)
    graph.add_node("validate_candidate", validate, retry_policy=None)
    graph.add_edge(START, "prepare_input")
    graph.add_edge("prepare_input", "model_request")
    graph.add_edge("model_request", "validate_candidate")
    graph.add_edge("validate_candidate", END)
    return graph.compile(checkpointer=None, name="corvus_analyst")


_GRAPH = build_graph()


def analyze(bundle, model: AnalystModel, *, on_reply=None, input_snapshot=None, on_step=None):
    identifier = (input_snapshot or {}).get("workflow", {}).get("id", "analyst.single_pass.v1")
    if identifier == "analyst.agentic.v1":
        from .agentic import investigate

        return investigate(
            bundle, model, input_snapshot=input_snapshot, on_reply=on_reply, on_step=on_step
        )
    if identifier != "analyst.single_pass.v1":
        raise ValueError("Unsupported approved workflow")
    # External tracing must not create a second, unapproved evidence destination.
    with tracing_context(enabled=False):
        state = _GRAPH.invoke(
            {
                "bundle": bundle,
                "model": model,
                "on_reply": on_reply,
                "input_snapshot": input_snapshot,
            },
            config={"recursion_limit": 8, "callbacks": []},
        )
    return state["result"]
