"""Tool schema shared with model providers."""

from typing import Any

from pydantic import BaseModel, Field


class Tool(BaseModel):
    """Provider-agnostic tool definition.

    `parameters` is a JSON Schema dict describing the tool's arguments.
    """

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
