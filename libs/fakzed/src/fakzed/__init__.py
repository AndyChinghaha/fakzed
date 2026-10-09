"""Fakzed: a lightweight framework for building agent platforms.

Named after Faker's legendary Zed outplay. Three primitives — Agent, Team,
Workflow — with pluggable capabilities (models, tools, memory, knowledge,
guardrails), sharing one registration mechanism between SDK and platform.
"""

from importlib.metadata import version as _version

from fakzed.agent import Agent, MemberInteraction, RunResponse, Team, TeamRoute
from fakzed.context import ContextProvider, TimeProvider
from fakzed.evals import EvalCase, EvalReport, eval_agent
from fakzed.guardrails import (
    GuardrailError,
    GuardrailResult,
    Guardrails,
    InputGuardrail,
    OutputGuardrail,
)
from fakzed.hooks import Hooks
from fakzed.knowledge import (
    Embedder,
    HashEmbedder,
    InMemoryVectorDb,
    KnowledgeBase,
    OpenAIEmbedder,
    SearchResult,
    VectorDb,
)
from fakzed.memory import AgenticMemory
from fakzed.model import Message, Model, create_model
from fakzed.observability import (
    EventBus,
    MetricsCollector,
    RunEvent,
    RunMetrics,
    RunObserver,
    Trace,
    Tracer,
)
from fakzed.platform import RemoteAgent, RemoteAgentError
from fakzed.runtime import BackgroundRun, BackgroundRunner, Scheduler
from fakzed.session import Session
from fakzed.skills import Skill
from fakzed.storage import InMemoryStorage, SqliteStorage, Storage
from fakzed.tools import Tool, tool
from fakzed.workflow import (
    IfBlock,
    LoopBlock,
    ParallelBlock,
    Step,
    Workflow,
    WorkflowContext,
    WorkflowResult,
)

__version__ = _version("fakzed")

__all__ = [
    "Agent",
    "RunResponse",
    "Team",
    "MemberInteraction",
    "TeamRoute",
    "AgenticMemory",
    "ContextProvider",
    "TimeProvider",
    "KnowledgeBase",
    "Embedder",
    "HashEmbedder",
    "OpenAIEmbedder",
    "VectorDb",
    "InMemoryVectorDb",
    "SearchResult",
    "Message",
    "Model",
    "create_model",
    "Session",
    "Skill",
    "Storage",
    "InMemoryStorage",
    "SqliteStorage",
    "Tool",
    "tool",
    "Workflow",
    "Step",
    "IfBlock",
    "LoopBlock",
    "ParallelBlock",
    "WorkflowContext",
    "WorkflowResult",
    "Hooks",
    "Guardrails",
    "InputGuardrail",
    "OutputGuardrail",
    "GuardrailResult",
    "GuardrailError",
    "EventBus",
    "RunEvent",
    "RunMetrics",
    "RunObserver",
    "MetricsCollector",
    "Tracer",
    "Trace",
    "RemoteAgent",
    "RemoteAgentError",
    "BackgroundRunner",
    "BackgroundRun",
    "Scheduler",
    "eval_agent",
    "EvalCase",
    "EvalReport",
]
