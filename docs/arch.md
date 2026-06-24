# AgeOS Architecture

AgeOS is innovative because it combines three things in one runtime:

1. local LLM serving,
2. shared warm-model orchestration, and
3. sandboxed agents that can still use local inference safely.

## High-level diagram

```mermaid
flowchart TB
    user([Developer or App])

    subgraph host[Host runtime]
        cli[AgeOS CLI + OpenAI-compatible API]
        py[Python control plane<br/>config, UX, downloads]
        native[libageos native core<br/>scheduler, warm cache, sandbox]
        models[(Local model backends)]
    end

    subgraph sandbox[Sandboxed agent environment]
        agent[Agent process]
        workspace[(Workspace + persistent agent home)]
    end

    user --> cli
    cli --> py
    py --> native
    native --> models
    native --> agent
    agent --> workspace
    agent -. local inference only .-> cli

    classDef entry fill:#e8f1ff,stroke:#2457c5,stroke-width:2px,color:#0f172a;
    classDef control fill:#eefce8,stroke:#2e7d32,stroke-width:2px,color:#0f172a;
    classDef core fill:#fff4db,stroke:#c77800,stroke-width:2px,color:#0f172a;
    classDef runtime fill:#f4e8ff,stroke:#7b3fc6,stroke-width:2px,color:#0f172a;
    classDef data fill:#fff,stroke:#475569,stroke-width:1.5px,color:#0f172a;

    class user entry;
    class cli,py control;
    class native core;
    class agent runtime;
    class models,workspace data;
```

## Why this is different

- **One entrypoint, multiple surfaces**: the CLI, SDK-style flows, and OpenAI-compatible endpoint all converge on the same runtime.
- **Warm local models**: model backends stay reusable across prompts and agent runs instead of being restarted for every request.
- **Native sandboxing**: agents run with restricted filesystem and network access while still getting access to the local inference endpoint.
- **Clear separation of roles**: Python handles user-facing orchestration, while `libageos` owns scheduling, model lifecycle, and sandbox enforcement.
