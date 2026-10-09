"""Toolkits: themed bundles of tools plus optional usage instructions."""

from pydantic import BaseModel, ConfigDict, Field

from fakzed.tools.tool import Tool


class ToolKit(BaseModel):
    """A themed collection of tools (web, files, finance, ...) used on demand.

    Attach via `Agent.toolkits`: the tools merge into the agent's tool set and
    the instructions are injected into the system prompt.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str | None = None
    instructions: str | None = None
    tools: list[Tool] = Field(default_factory=list)

    def get_tools(self) -> list[Tool]:
        """The tools in this toolkit."""
        return self.tools

    def get_instructions(self) -> str | None:
        """Usage instructions for the model, if any."""
        return self.instructions
