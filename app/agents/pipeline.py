import asyncio
import time
from typing import Any
from app.agents.groq_agent import run_groq_analysis
from app.agents.gemini_agent import run_gemini_analysis
from app.agents.slither_agent import run_slither_analysis

# 6 specialist agents mapped to vulnerability categories
AGENT_CONFIGS = [
    {"name": "reentrancy_agent",    "focus": "reentrancy attacks and cross-function reentrancy"},
    {"name": "overflow_agent",      "focus": "integer overflow, underflow, and arithmetic vulnerabilities"},
    {"name": "access_control_agent","focus": "access control, ownership, privilege escalation"},
    {"name": "logic_agent",         "focus": "business logic flaws, flash loan attacks, price manipulation"},
    {"name": "gas_agent",           "focus": "gas griefing, denial of service, unbounded loops"},
    {"name": "defi_agent",          "focus": "DeFi-specific: oracle manipulation, MEV, sandwich attacks"},
]

RISK_THRESHOLDS = {
    "critical": 80,
    "high": 60,
    "medium": 35,
    "low": 10
}

async def run_audit_pipeline(contract_code: str, contract_name: str = "Contract") -> dict:
    start_time = time.time()
    all_findings = []
    agents_used = []

    # Run Groq agents in parallel (6 agents, 2 per batch to respect rate limits)
    groq_tasks = []
    for agent in AGENT_CONFIGS:
        groq_tasks.append(
            run_groq_analysis(contract_code, agent["focus"], agent["name"])
        )

    # Run Gemini + Slither concurrently with Groq
    groq_results, gemini_result, slither_result = await asyncio.gather(
        asyncio.gather(*groq_tasks, return_exceptions=True),
        run_gemini_analysis(contract_code),
        run_slither_analysis(contract_code),
        return_exceptions=True
    )

    # Collect Groq findings
    if isinstance(groq_results, list):
        for i, res in enumerate(groq_results):
            if isinstance(res, Exception):
                print(f"Groq agent {AGENT_CONFIGS[i]['name']} error: {res}")
                continue
            if res and isinstance(res, list):
                all_findings.extend(res)
                agents_used.append(AGENT_CONFIGS[i]["name"])

    # Collect Gemini findings
    if not isinstance(gemini_result, Exception) and isinstance(gemini_result, list):
        all_findings.extend(gemini_result)
        agents_used.append("gemini_agent")

    # Collect Slither findings
    if not isinstance(slither_result, Exception) and isinstance(slither_result, list):
        all_findings.extend(slither_result)
        agents_used.append("slither_agent")

    # Deduplicate findings by type + line
    seen = set()
    unique_findings = []
    for f in all_findings:
        key = (f.get("type", ""), f.get("line", ""), f.get("severity", ""))
        if key not in seen:
            seen.add(key)
            unique_findings.append(f)

    # Count by severity
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in unique_findings:
        sev = f.get("severity", "info").lower()
        if sev in counts:
            counts[sev] += 1

    # Calculate risk score (weighted)
    risk_score = min(100, (
        counts["critical"] * 25 +
        counts["high"] * 12 +
        counts["medium"] * 5 +
        counts["low"] * 2
    ))

    # Determine risk level
    if risk_score >= RISK_THRESHOLDS["critical"]:
        risk_level = "critical"
    elif risk_score >= RISK_THRESHOLDS["high"]:
        risk_level = "high"
    elif risk_score >= RISK_THRESHOLDS["medium"]:
        risk_level = "medium"
    elif risk_score >= RISK_THRESHOLDS["low"]:
        risk_level = "low"
    else:
        risk_level = "info"

    scan_duration = int((time.time() - start_time) * 1000)

    summary = f"Analyzed {contract_name} using {len(agents_used)} agents. "
    summary += f"Found {len(unique_findings)} issues: "
    summary += f"{counts['critical']} critical, {counts['high']} high, "
    summary += f"{counts['medium']} medium, {counts['low']} low."

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "total_findings": len(unique_findings),
        "critical_count": counts["critical"],
        "high_count": counts["high"],
        "medium_count": counts["medium"],
        "low_count": counts["low"],
        "findings": unique_findings,
        "summary": summary,
        "agents_used": agents_used,
        "scan_duration_ms": scan_duration
    }
