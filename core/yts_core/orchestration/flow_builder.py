from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import StateGraph


@dataclass(frozen=True)
class FlowSpec:
    """A reusable LangGraph topology declaration."""

    name: str
    state_type: type
    stages: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]


def build_flow_graph(spec: FlowSpec, nodes: object, *, checkpointer=None):
    """Compile a StateGraph from a flow spec and a node provider object."""

    _validate_flow_spec(spec)
    graph = StateGraph(spec.state_type)
    for stage in spec.stages:
        node = _node_callable(nodes, stage, spec.name)
        graph.add_node(stage, node)
    for start, end in spec.edges:
        graph.add_edge(start, end)
    return graph.compile(checkpointer=checkpointer, name=spec.name)


def workflow_config(
    *,
    checkpointer,
    thread_id: str | None = None,
    run_id: str | None = None,
    checkpoint_ns: str | None = None,
    checkpoint_id: str | None = None,
) -> dict[str, Any] | None:
    """Build LangGraph runtime config for checkpoint-aware invocations."""

    needs_thread_id = (
        checkpointer is not None or checkpoint_ns is not None or checkpoint_id is not None
    )
    if not needs_thread_id and thread_id is None and run_id is None:
        return None

    if thread_id is None or not thread_id.strip():
        raise ValueError("thread_id is required when LangGraph checkpointer is enabled")

    configurable: dict[str, Any] = {"thread_id": thread_id.strip()}
    if run_id is not None:
        configurable["run_id"] = _non_empty_runtime_id(run_id, "run_id")
    if checkpoint_ns is not None:
        configurable["checkpoint_ns"] = _runtime_id(checkpoint_ns, "checkpoint_ns")
    if checkpoint_id is not None:
        configurable["checkpoint_id"] = _non_empty_runtime_id(checkpoint_id, "checkpoint_id")
    return {"configurable": configurable}


def _validate_flow_spec(spec: FlowSpec) -> None:
    if not spec.name.strip():
        raise ValueError("flow spec name must not be empty")
    if not spec.stages:
        raise ValueError(f"flow {spec.name} must declare at least one stage")
    seen: set[str] = set()
    for stage in spec.stages:
        if not stage.strip():
            raise ValueError(f"flow {spec.name} contains an empty stage name")
        if stage in seen:
            raise ValueError(f"flow {spec.name} contains duplicate stage: {stage}")
        seen.add(stage)


def _node_callable(nodes: object, stage: str, flow_name: str):
    node = getattr(nodes, stage, None)
    if not callable(node):
        raise TypeError(f"flow {flow_name} node {stage} is not callable")
    return node


def _runtime_id(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value.strip()


def _non_empty_runtime_id(value: str, label: str) -> str:
    runtime_id = _runtime_id(value, label)
    if not runtime_id:
        raise ValueError(f"{label} must not be empty")
    return runtime_id
