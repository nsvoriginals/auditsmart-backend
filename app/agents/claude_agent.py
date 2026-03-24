"""
AuditSmart v3.0 — Claude (Anthropic) Agent

Plan routing:
  free       → NOT called (uses Gemini)
  pro        → claude-haiku  (fast summary + fix suggestions)
  enterprise → claude-sonnet (deep analysis + fix suggestions)
  deep_audit → claude-opus   (superior full analysis, all agents, Extended Thinking)

Features used:
  - Prompt Caching    → System prompt cached → ~80% cost saving on repeat calls
  - Tool Use          → Guaranteed structured JSON (zero parsing errors)
  - Extended Thinking → Deep Audit only — shows full AI reasoning chain
  - 200K Context      → Full contract, no truncation
"""

import asyncio
import anthropic
from app.config import settings


_client = None


def get_client() -> anthropic.AsyncAnthropic | None:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            return None
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def get_model_for_plan(plan: str) -> str:
    return {
        "pro":        settings.CLAUDE_HAIKU_MODEL,
        "enterprise": settings.CLAUDE_SONNET_MODEL,
        "deep_audit": settings.CLAUDE_OPUS_MODEL,
    }.get(plan, settings.CLAUDE_HAIKU_MODEL)


# ── CACHED SYSTEM PROMPT ───────────────────────────────────────────────────────
# cache_control = "ephemeral" → Anthropic caches this for 5 minutes
# All 3 Claude calls share this cache → ~80% discount on input tokens
SYSTEM_PROMPT_CACHED = [
    {
        "type": "text",
        "text": """You are the world's most advanced Solidity smart contract security auditor.
You have discovered critical vulnerabilities in DeFi protocols managing billions of dollars.

YOUR MISSION:
- Find REAL exploitable vulnerabilities — not theoretical concerns
- Every finding must include exact function name, exploit path, and specific code fix
- Severity must reflect actual financial/operational impact
- Do NOT duplicate findings already identified

SEVERITY GUIDE:
  critical → Direct fund theft, rug pull, total compromise
  high     → Significant fund loss, privilege escalation
  medium   → Limited fund risk, logic errors, economic attacks
  low      → Best practices, gas optimizations
  info     → Documentation, style, informational

Always use the provided tool. Never add prose outside tool calls.""",
        "cache_control": {"type": "ephemeral"}
    }
]


# ── TOOL DEFINITIONS ──────────────────────────────────────────────────────────
def get_audit_tool(include_exploit: bool = False) -> dict:
    """Tool definition — richer for Enterprise/Deep Audit."""
    properties = {
        "type":           {"type": "string", "description": "Vulnerability name"},
        "severity":       {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
        "function":       {"type": "string", "description": "Affected function name"},
        "line":           {"type": "string", "description": "Line number or range"},
        "description":    {"type": "string", "description": "What is wrong and exact exploit path"},
        "recommendation": {"type": "string", "description": "Specific code fix"},
    }
    if include_exploit:
        properties["exploit_scenario"] = {
            "type": "string",
            "description": "Step-by-step attacker walkthrough"
        }
        properties["fix_code_snippet"] = {
            "type": "string",
            "description": "Exact patched code snippet ready to use"
        }

    return {
        "name": "report_findings",
        "description": "Report all security vulnerabilities found in the smart contract",
        "input_schema": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": properties,
                        "required": ["type", "severity", "function", "description", "recommendation"]
                    }
                },
                "overall_assessment": {
                    "type": "string",
                    "description": "2-3 sentence executive summary of contract security"
                },
                "deployment_recommendation": {
                    "type": "string",
                    "enum": ["SAFE TO DEPLOY", "DEPLOY WITH CAUTION", "DO NOT DEPLOY"],
                    "description": "Clear deployment verdict"
                }
            },
            "required": ["findings", "overall_assessment", "deployment_recommendation"]
        }
    }


# ── PRO PLAN: Claude Haiku Orchestrator ───────────────────────────────────────
async def run_claude_pro(
    contract_code: str,
    groq_findings: list[dict]
) -> dict:
    """
    Pro plan — Claude Haiku.
    Reviews Groq findings, adds missing issues, generates fix suggestions.
    Fast and cost-effective.
    """
    client = get_client()
    if not client:
        return {"findings": [], "summary": "", "verdict": ""}

    groq_summary = _format_findings_for_prompt(groq_findings, limit=20)

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=settings.CLAUDE_HAIKU_MODEL,
                max_tokens=3000,
                system=SYSTEM_PROMPT_CACHED,
                tools=[get_audit_tool(include_exploit=False)],
                tool_choice={"type": "any"},
                messages=[{
                    "role": "user",
                    "content": f"""Review this Solidity contract security audit.

FINDINGS FROM SPECIALIST AGENTS:
{groq_summary}

YOUR TASK:
1. Find any critical/high issues the agents missed
2. Validate existing findings
3. Focus on: access control, economic attacks, upgrade risks

CONTRACT:
```solidity
{contract_code[:8000]}
```

Use report_findings tool."""
                }]
            ),
            timeout=settings.CLAUDE_TIMEOUT_SECONDS
        )

        return _extract_tool_result(response, plan="pro")

    except Exception as e:
        print(f"❌ Claude Pro error: {e}")
        return {"findings": [], "summary": "", "verdict": ""}


# ── ENTERPRISE PLAN: Claude Sonnet Orchestrator ───────────────────────────────
async def run_claude_enterprise(
    contract_code: str,
    groq_findings: list[dict]
) -> dict:
    """
    Enterprise plan — Claude Sonnet.
    Deep analysis + exploit scenarios + fix code snippets.
    """
    client = get_client()
    if not client:
        return {"findings": [], "summary": "", "verdict": ""}

    groq_summary = _format_findings_for_prompt(groq_findings, limit=30)

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=settings.CLAUDE_SONNET_MODEL,
                max_tokens=6000,
                system=SYSTEM_PROMPT_CACHED,
                tools=[get_audit_tool(include_exploit=True)],
                tool_choice={"type": "any"},
                messages=[{
                    "role": "user",
                    "content": f"""Perform deep orchestration review of this smart contract.

SPECIALIST AGENT FINDINGS:
{groq_summary}

YOUR TASKS:
1. Find ALL additional vulnerabilities the specialist agents missed
2. For each critical/high finding: provide step-by-step exploit scenario
3. For each finding: provide exact patched code snippet
4. Cross-contract interaction risks
5. Economic attack vectors (flash loans, MEV, sandwich attacks)
6. Governance attack scenarios
7. Upgrade/proxy risks

CONTRACT (full source):
```solidity
{contract_code}
```

Use report_findings tool with full exploit scenarios and fix code."""
                }]
            ),
            timeout=settings.CLAUDE_TIMEOUT_SECONDS
        )

        return _extract_tool_result(response, plan="enterprise")

    except Exception as e:
        print(f"❌ Claude Enterprise error: {e}")
        return {"findings": [], "summary": "", "verdict": ""}


# ── DEEP AUDIT: Claude Opus + Extended Thinking ───────────────────────────────
async def run_claude_deep_audit(
    contract_code: str,
    groq_findings: list[dict]
) -> dict:
    """
    Deep Audit — $20/audit add-on.
    Claude Opus + Extended Thinking (8000 token budget).

    What makes this special:
    - Opus = most intelligent Claude model
    - Extended Thinking = Claude shows its full reasoning chain
    - User can SEE how Claude analyzed their contract step by step
    - This is the marketing differentiator — no competitor offers this
    """
    client = get_client()
    if not client:
        return {"findings": [], "summary": "", "verdict": "", "thinking": None}

    groq_summary = _format_findings_for_prompt(groq_findings, limit=30)

    print("   🧠 Deep Audit: Claude Opus + Extended Thinking activated")

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=settings.CLAUDE_OPUS_MODEL,
                max_tokens=16000,       # Higher limit for thinking + output
                thinking={
                    "type": "enabled",
                    "budget_tokens": 8000  # Opus gets 8K tokens to reason deeply
                },
                system=SYSTEM_PROMPT_CACHED,
                tools=[get_audit_tool(include_exploit=True)],
                tool_choice={"type": "any"},
                messages=[{
                    "role": "user",
                    "content": f"""DEEP SECURITY AUDIT — Maximum thoroughness required.

This is a paid premium audit. The user is about to deploy to mainnet.
Find EVERY possible vulnerability. Leave nothing unchecked.

FINDINGS FROM SPECIALIST AGENTS (validate and expand):
{groq_summary}

COMPLETE AUDIT REQUIREMENTS:
1. Every vulnerability class: reentrancy, overflow, access control, logic, DoS, oracle, MEV, flash loans, signatures, upgrades, governance
2. For critical/high: exact step-by-step exploit with transaction sequence
3. For every finding: production-ready patched code
4. Economic attack modeling: what is maximum extractable value?
5. Interaction risks: how does this contract behave with malicious tokens/contracts?
6. Deployment checklist: what must be fixed before mainnet?

CONTRACT (full source — analyze COMPLETELY):
```solidity
{contract_code}
```

Think deeply and thoroughly before using report_findings tool.
This user is paying $20 for the best possible analysis."""
                }]
            ),
            timeout=180  # More time for Opus + thinking
        )

        result = _extract_tool_result(response, plan="deep_audit")

        # Extract Extended Thinking chain
        thinking_blocks = []
        for block in response.content:
            if hasattr(block, 'type') and block.type == "thinking":
                thinking_blocks.append(block.thinking)

        if thinking_blocks:
            result["thinking"] = "\n\n---\n\n".join(thinking_blocks)
            print(f"   🧠 Thinking chain captured: {len(result['thinking'])} chars")
        else:
            result["thinking"] = None

        return result

    except Exception as e:
        print(f"❌ Claude Deep Audit error: {e}")
        return {"findings": [], "summary": "", "verdict": "", "thinking": None}


# ── MAIN DISPATCHER ───────────────────────────────────────────────────────────
async def run_claude_analysis(
    contract_code: str,
    groq_findings: list[dict],
    plan: str
) -> dict:
    """
    Dispatch to correct Claude function based on plan.
    Free plan → returns empty (Gemini handles it)
    """
    if plan == "free":
        return {"findings": [], "summary": "", "verdict": "", "thinking": None}
    elif plan == "pro":
        return await run_claude_pro(contract_code, groq_findings)
    elif plan == "enterprise":
        return await run_claude_enterprise(contract_code, groq_findings)
    elif plan == "deep_audit":
        return await run_claude_deep_audit(contract_code, groq_findings)
    else:
        return {"findings": [], "summary": "", "verdict": "", "thinking": None}


# ── HELPERS ───────────────────────────────────────────────────────────────────
def _format_findings_for_prompt(findings: list[dict], limit: int = 25) -> str:
    if not findings:
        return "No findings from specialist agents yet."
    lines = []
    for i, f in enumerate(findings[:limit], 1):
        lines.append(
            f"{i}. [{f.get('severity','?').upper()}] {f.get('type','Unknown')} "
            f"in {f.get('function','?')} — {f.get('description','')[:150]}"
        )
    if len(findings) > limit:
        lines.append(f"... and {len(findings) - limit} more findings")
    return "\n".join(lines)


def _extract_tool_result(response, plan: str) -> dict:
    findings = []
    summary = ""
    verdict = ""

    for block in response.content:
        if hasattr(block, 'type') and block.type == "tool_use" and block.name == "report_findings":
            inp = block.input
            raw = inp.get("findings", [])
            summary = inp.get("overall_assessment", "")
            verdict = inp.get("deployment_recommendation", "")

            for f in raw:
                f["source"] = f"claude_{plan}"
                f["ai_enhanced"] = True
                # Normalize auto_fix for Pro+
                if f.get("fix_code_snippet"):
                    f["auto_fix"] = {
                        "fixed_code":  f.pop("fix_code_snippet"),
                        "explanation": f.get("recommendation", ""),
                        "generated_by": f"claude_{plan}"
                    }
            findings = raw

    print(f"   ✅ Claude ({plan}): {len(findings)} findings | verdict: {verdict}")
    return {
        "findings": findings,
        "summary":  summary,
        "verdict":  verdict,
        "thinking": None
    }
