"""Skills: composable capability units injected into the agent's prompt."""

from pydantic import BaseModel, ConfigDict


class Skill(BaseModel):
    """A reusable capability that augments an agent via prompt injection.

    Attaching a skill to an agent adds its instructions to the system prompt,
    teaching the agent how to handle a domain (e.g. legal drafting, SQL
    review). Tool functions that belong to the skill are attached separately
    as regular tools.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    instructions: str
