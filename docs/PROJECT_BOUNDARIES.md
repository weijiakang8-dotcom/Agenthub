# Project Boundaries

AgentHub is an independent product and repository. Its source tree, build system, runtime services, deployment configuration, credentials, and data stores must remain self-contained.

Factory RCA Agent is a separate product. It is not an AgentHub package, example application, deployment component, test fixture, or runtime dependency.

## Repository rules

- Do not add Factory RCA source code, industrial case data, knowledge-base files, CI workflows, Compose services, secrets, or generated artifacts to this repository.
- Do not share Git branches, tags, worktrees, deployment directories, databases, Redis namespaces, container names, ports, or environment files between the two products.
- Cross-project integration, if introduced later, must use a documented external API and must not vendor either product into the other repository.
- Changes to these boundaries require an architecture decision record and an explicit security review.

## AgentHub ownership

The AgentHub repository owns the multi-agent collaboration platform, including its web application, API, execution runtimes, model routing, MCP integration, skills, approval controls, observability, and AgentHub-specific deployment assets.
