"""
AuditSmart v3.0 — Audit Pipeline

Plan Routing:
  free       → 8 Groq agents + Gemini orchestrator
  pro        → 8 Groq agents + Claude Haiku (fix suggestions included)
  enterprise → 8 Groq agents + Claude Sonnet (exploit scenarios + fix code)
  deep_audit → 8 Groq agents + Claude Opus + Extended Thinking (superior)
"""

import asyncio
import time
from app.agents.groq_agent import run_groq_analysis
from app.agents.gemini_agent import run_gemini_analysis
from app.agents.claude_agent import run_claude_analysis
from app.agents.slither_agent import run_slither_analysis
from app.services.dedup_engine import deduplicate_and_validate
from app.services.pdf_generator import generate_audit_pdf, pdf_to_base64, REPORTLAB_AVAILABLE
from app.config import settings

AGENT_CONFIGS = [
    {
        "name": "reentrancy_agent",
        "focus": (
            "Reentrancy attacks: Check EVERY function that makes external calls "
            "(call, send, transfer). Is state updated BEFORE or AFTER the call? "
            "Check for cross-function reentrancy. Check if nonReentrant modifier "
            "is applied to ALL functions that need it. "
            "If a function already has nonReentrant, do NOT report reentrancy for it."
        )
    },
    {
        "name": "overflow_agent",
        "focus": (
            "Integer overflow/underflow: Check all arithmetic operations. "
            "Look for 'unchecked' blocks that bypass Solidity 0.8+ protections. "
            "Check division by zero. Check precision loss in calculations. "
            "Check share rounding to zero attacks."
        )
    },
    {
        "name": "access_control_agent",
        "focus": (
            "Access control: Check EVERY public/external function. "
            "Can anyone call pause/unpause? Can anyone call initialize? "
            "Is ownership transfer single-step or two-step? "
            "Can owner set fees above 100%? Are there unused state variables like pendingOwner?"
        )
    },
    {
        "name": "logic_agent",
        "focus": (
            "Business logic flaws: Check deposit/withdraw accounting. "
            "Can emergency withdraw break accounting? "
            "Check share price manipulation — can first depositor inflate share price? "
            "Check flash loan repayment logic. Can ETH sent via selfdestruct bypass balance checks?"
        )
    },
    {
        "name": "gas_dos_agent",
        "focus": (
            "Gas griefing and DoS: Check for unbounded arrays. "
            "Check loops over arrays with external calls. "
            "Check reward distribution over all depositors. "
            "Check silent transfer failures — are failed ETH sends ignored?"
        )
    },
    {
        "name": "defi_agent",
        "focus": (
            "DeFi vulnerabilities: Check oracle manipulation. "
            "Is price oracle validated? Is there staleness checking? "
            "Check MEV/sandwich attack vectors. "
            "Check if receive()/fallback() accept ETH without accounting. "
            "Check unsafe ERC20 — does transferFrom check return value?"
        )
    },
    {
        "name": "backdoor_agent",
        "focus": (
            "BACKDOOR DETECTION — CRITICAL: "
            "1) selfdestruct — lets owner drain all funds. "
            "2) delegatecall to arbitrary addresses. "
            "3) arbitrary calldata in governance proposals. "
            "4) quorum = 1 vote to pass proposals. "
            "5) migration functions that move all funds. "
            "Report ALL as CRITICAL severity."
        )
    },
    {
        "name": "signature_agent",
        "focus": (
            "Signature vulnerabilities: "
            "1) ecrecover — does it verify signer != address(0)? "
            "2) Replay protection — is there a nonce? "
            "3) Cross-chain replay — is chainId included? "
            "4) abi.encodePacked with variable-length types — hash collisions. "
            "5) EIP-712 compliance."
        )
    },
]

RISK_THRESHOLDS = {"critical": 80, "high": 60, "medium": 35, "low": 10}


async def run_audit_pipeline(
    contract_code: str,
    contract_name: str = "Contract",
    plan: str = "free"
) -> dict:
    start_time = time.time()
    all_findings = []
    agents_used = []

    print("\n" + "=" * 65)
    print(f"🚀 AuditSmart v3.0 | {contract_name} | Plan: {plan.upper()}")
    print(f"   Contract: {len(contract_code)} chars")
    print(f"   Groq: {'✅' if settings.GROQ_API_KEY else '❌'} | "
          f"Gemini: {'✅' if settings.GEMINI_API_KEY else '❌'} | "
          f"Claude: {'✅' if settings.ANTHROPIC_API_KEY else '❌'}")
    print("=" * 65)

    # ── PHASE 1: 8 Groq Agents + Slither (ALL plans) ─────────────────────────
    print("\n📡 Phase 1: 8 Groq agents + Slither (parallel)...")
    groq_tasks = [
        run_groq_analysis(contract_code, agent["focus"], agent["name"])
        for agent in AGENT_CONFIGS
    ]

    groq_results, slither_result = await asyncio.gather(
        asyncio.gather(*groq_tasks, return_exceptions=True),
        run_slither_analysis(contract_code),
        return_exceptions=True
    )

    # Collect Groq
    if isinstance(groq_results, list):
        for i, res in enumerate(groq_results):
            if isinstance(res, Exception):
                print(f"   ❌ {AGENT_CONFIGS[i]['name']}: {res}")
                continue
            if res and isinstance(res, list):
                all_findings.extend(res)
                agents_used.append(AGENT_CONFIGS[i]["name"])
                print(f"   ✅ {AGENT_CONFIGS[i]['name']}: {len(res)} findings")

    # Collect Slither
    if not isinstance(slither_result, Exception) and isinstance(slither_result, list):
        all_findings.extend(slither_result)
        agents_used.append("slither_agent")
        print(f"   ✅ slither_agent: {len(slither_result)} findings")

    print(f"\n   Phase 1 total: {len(all_findings)} raw findings")

    # ── PHASE 2: AI Orchestrator (plan-based) ─────────────────────────────────
    thinking_chain = None

    if plan == "free":
        # Free → Gemini
        print("\n🤖 Phase 2: Gemini Orchestrator (Free plan)...")
        gemini_result = await run_gemini_analysis(contract_code)
        if isinstance(gemini_result, list) and gemini_result:
            all_findings.extend(gemini_result)
            agents_used.append("gemini_agent")
            print(f"   ✅ gemini_agent: {len(gemini_result)} findings")

    elif plan in ("pro", "enterprise", "deep_audit"):
        # Pro/Enterprise/Deep → Claude
        labels = {
            "pro":        "Claude Haiku",
            "enterprise": "Claude Sonnet",
            "deep_audit": "Claude Opus + Extended Thinking 🧠"
        }
        print(f"\n🤖 Phase 2: {labels[plan]} ({plan})...")
        claude_result = await run_claude_analysis(
            contract_code=contract_code,
            groq_findings=all_findings,
            plan=plan
        )

        claude_findings = claude_result.get("findings", [])
        if claude_findings:
            all_findings.extend(claude_findings)
            agents_used.append(f"claude_{plan}")
            print(f"   ✅ claude_{plan}: {len(claude_findings)} additional findings")

        thinking_chain = claude_result.get("thinking")
        claude_verdict = claude_result.get("verdict", "")
        claude_summary = claude_result.get("summary", "")
    else:
        claude_verdict = ""
        claude_summary = ""

    # ── DEDUPLICATION ─────────────────────────────────────────────────────────
    print(f"\n🔍 Deduplication: {len(all_findings)} raw → ", end="")
    unique_findings = deduplicate_and_validate(all_findings, contract_code)
    print(f"{len(unique_findings)} unique")

    # ── SCORING ───────────────────────────────────────────────────────────────
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in unique_findings:
        sev = f.get("severity", "info").lower()
        if sev in counts:
            counts[sev] += 1

    risk_score = min(100, (
        counts["critical"] * 25 +
        counts["high"] * 12 +
        counts["medium"] * 5 +
        counts["low"] * 2
    ))

    if risk_score >= RISK_THRESHOLDS["critical"]:   risk_level = "critical"
    elif risk_score >= RISK_THRESHOLDS["high"]:      risk_level = "high"
    elif risk_score >= RISK_THRESHOLDS["medium"]:    risk_level = "medium"
    elif risk_score >= RISK_THRESHOLDS["low"]:       risk_level = "low"
    else:                                            risk_level = "info"

    scan_duration = int((time.time() - start_time) * 1000)

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    summary = (
        claude_summary if plan != "free" and claude_summary
        else (
            f"Analyzed {contract_name} using {len(agents_used)} agents. "
            f"Found {len(unique_findings)} unique issues: "
            f"{counts['critical']} critical, {counts['high']} high, "
            f"{counts['medium']} medium, {counts['low']} low."
        )
    )

    result = {
        "risk_level":          risk_level,
        "risk_score":          risk_score,
        "total_findings":      len(unique_findings),
        "raw_findings_count":  len(all_findings),
        "critical_count":      counts["critical"],
        "high_count":          counts["high"],
        "medium_count":        counts["medium"],
        "low_count":           counts["low"],
        "info_count":          counts["info"],
        "findings":            unique_findings,
        "summary":             summary,
        "agents_used":         agents_used,
        "scan_duration_ms":    scan_duration,
        "plan_used":           plan,
        # Pro/Enterprise/Deep Audit extras
        "has_fix_suggestions": any(f.get("auto_fix") for f in unique_findings),
        "deployment_verdict":  claude_verdict if plan != "free" else "",
        # Deep Audit exclusive
        "thinking_chain":      thinking_chain,
        "is_deep_audit":       plan == "deep_audit",
    }

    # ── PDF GENERATION ─────────────────────────────────────────────────────────
    if REPORTLAB_AVAILABLE and settings.PDF_ENABLED:
        try:
            print("📄 Generating PDF report...")
            pdf_bytes = generate_audit_pdf(result)
            if pdf_bytes:
                result["pdf_base64"] = pdf_to_base64(pdf_bytes)
                result["pdf_available"] = True
                print(f"   ✅ PDF: {len(pdf_bytes):,} bytes")
            else:
                result["pdf_available"] = False
        except Exception as e:
            print(f"   ❌ PDF error: {e}")
            result["pdf_available"] = False
    else:
        result["pdf_available"] = False

    print("\n" + "=" * 65)
    print(f"✅ AUDIT COMPLETE | Risk: {risk_level.upper()} ({risk_score}/100) | "
          f"Duration: {scan_duration}ms")
    print(f"   {counts['critical']}C | {counts['high']}H | {counts['medium']}M | {counts['low']}L | "
          f"Fixes: {'✅' if result['has_fix_suggestions'] else '❌'} | "
          f"Thinking: {'✅' if thinking_chain else '❌'}")
    print("=" * 65 + "\n")

    return result
