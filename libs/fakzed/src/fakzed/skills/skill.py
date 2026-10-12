"""Skills: composable capability units injected into the agent's prompt."""

from pydantic import BaseModel, ConfigDict, Field

from fakzed.tools import Tool


class Skill(BaseModel):
    """A reusable capability that augments an agent via prompt injection.

    Attaching a skill to an agent adds its instructions to the system prompt,
    teaching the agent how to handle a domain (e.g. legal drafting, SQL
    review). A skill may bundle its own `tools`; they are merged into the
    agent's tool set automatically, so a capability ships as a single unit.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    instructions: str
    tools: list[Tool] = Field(default_factory=list)
