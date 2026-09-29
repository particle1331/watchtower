# agent-harness

Headless async coding-agent harness built in the agent-harness course.

The package exposes an OpenAI-compatible streaming client, a typed tool
registry, session state, context management, safety checks, hooks, sub-agents,
and optional MCP integration. It has no user interface or command-line entry
point yet.

```python
from agent_harness import Agent, Config

agent = Agent(Config())
```
