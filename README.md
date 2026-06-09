# Autonomous Vulnerability Remediation Engine (Devin API)

An event-driven automation platform built with FastAPI and Docker that polls GitHub issues, orchestrates Devin autonomous AI agents to remediate software vulnerabilities, and provides an executive operational dashboard tracking engineering throughput.

## System Architecture
- **Trigger Layer:** Continuous event-driven polling loop monitoring repository flags.
- **Orchestration Layer:** FastAPI service utilizing Devin v3 API endpoints for programmatic session management and state monitoring.
- **Observability Layer:** Real-time metrics UI answering: *"If I were an engineering leader, how would I know this is working?"*

## Quick Start (Local Simulation)

### 1. Prerequisites
Create a `.env` file in the root directory:
```env
DEVIN_API_KEY=cog_your_key_here
DEVIN_ORG_ID=org_your_id_here
GITHUB_PAT=github_pat_your_token_here
GITHUB_REPO=your_username/superset