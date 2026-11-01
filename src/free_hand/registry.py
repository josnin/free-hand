from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]
    risk: str = "read"
    def schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}

class Registry:
    def __init__(self): self._tools: dict[str, Tool] = {}
    def register(self, tool: Tool):
        if tool.name in self._tools: raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
    def get(self, name: str): return self._tools.get(name)
    def all(self): return list(self._tools.values())
