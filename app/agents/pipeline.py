"""
AuditSmart v2.0 — Multi-Agent Audit Pipeline

CHANGES from v1:
- 8 specialist agents (was 6) — added signature_agent and backdoor_agent
- Integrated deduplication engine (removes FPs and dupes)
- PDF report generation integrated
- Better agent focus prompts covering ALL missed categories
- Timeout handling per agent
"""

import asyncio
import time
from typing import Any
from app.agents.groq_agent import run_groq_analysis
from app.agents.gemini_agent import run_gemini_analysis
from app.agents.slither_agent import run_slither_analysis
from app.services.dedup_engine import deduplicate_and_validate
from app.services.pdf_generator import generate_audit_pdf, pdf_to_base64, REPORTLAB_AVAILABLE
from app.config import settings

# v2.0 — 8 specialist agents (added backdoor_agent and signature_agent)
AGENT_CONFIGS = [
    {
        "name": "reentrancy_agent",
        "focus": (
            "Reentrancy attacks: Check EVERY function that makes external calls "
            "(call, send, transfer). Is state updated BEFORE or AFTER the call? "
            "Check for cross-function reentrancy. Check if nonReentrant modifier "
            "is applied to ALL functions that need it — not just some. "
            "NOTE: If a function already has nonReentrant, do NOT report reentrancy for it."
        )
    },
    {
        "name": "overflow_agent",
        "focus": (
            "Integer overflow/underflow: Check all arithmetic operations. "
            "Look for 'unchecked' blocks that bypass Solidity 0.8+ protections. "
            "Check SafeMath-like libraries — do they use 'unchecked' internally? "
            "Check division by zero. Check precision loss in calculations like "
            "amount * shares / totalShares. Check share rounding to zero attacks."
        )
    },
    {
        "name": "access_control_agent",
        "focus": (
            "Access control vulnerabilities: Check EVERY public/external function. "
            "Does it have appropriate access control (onlyOwner, role-based)? "
            "CRITICAL: Can anyone call pause/unpause? Can anyone call initialize? "
            "Is ownership transfer single-step (dangerous) or two-step? "
            "Can owner set fees above 100%? Can owner lock withdrawals forever? "
            "Are there declared-but-unused state variables like pendingOwner? "
            "Is guardian variable initialized or stuck at address(0)?"
        )
    },
    {
        "name": "logic_agent",
        "focus": (
            "Business logic flaws: Check deposit/withdraw accounting — is totalDeposited "
            "always updated correctly? Can emergency withdraw break accounting? "
            "Check share price manipulation — can first depositor inflate share price? "
            "Check flash loan repayment logic — is the balance check correct? "
            "Can ETH sent via selfdestruct bypass balance checks? "
            "Check token deposit/withdraw — can users actually withdraw their tokens? "
            "Check delegation — can delegated shares still be withdrawn?"
        )
    },
    {
        "name": "gas_dos_agent",
        "focus": (
            "Gas griefing and Denial of Service: Check for unbounded arrays "
            "(depositors, strategies). Check for loops over mappings/arrays "
            "with external calls — can one failing call block all others? "
            "Check reward distribution — does it iterate all depositors? "
            "Check if duplicate entries can be added to arrays. "
            "Check silent transfer failures — are failed ETH sends ignored?"
        )
    },
    {
        "name": "defi_agent",
        "focus": (
            "DeFi-specific vulnerabilities: Check oracle manipulation — is price "
            "oracle validated? Is there staleness checking? Are returned values "
            "bounds-checked (not 0, not max uint)? Check for MEV/sandwich attack "
            "vectors. Check flash loan fee calculation. Check if receive()/fallback() "
            "accept ETH without accounting — this inflates share price silently. "
            "Check unsafe ERC20 interactions — does transferFrom check return value? "
            "Are fee-on-transfer tokens handled? Check for tokens getting permanently locked."
        )
    },
    {
        "name": "backdoor_agent",
        "focus": (
            "BACKDOOR DETECTION — THIS IS CRITICAL: "
            "1) Check for selfdestruct — this lets owner drain ALL funds instantly. "
            "   Any function using selfdestruct() is a CRITICAL rug-pull vector. "
            "2) Check for delegatecall to arbitrary addresses — this lets owner "
            "   execute any code and overwrite any storage slot including owner. "
            "3) Check for arbitrary external calls in governance — can a proposal "
            "   execute any calldata on any target address? "
            "4) Check quorum requirements — can 1 vote pass a proposal? "
            "5) Check migration/upgrade functions that move all funds. "
            "Report ALL of these as CRITICAL severity."
        )
    },
    {
        "name": "signature_agent",
        "focus": (
            "Signature and cryptographic vulnerabilities: "
            "1) Check ecrecover usage — does it verify signer != address(0)? "
            "   ecrecover returns 0x0 for invalid signatures. "
            "2) Check for replay protection — is there a nonce in the signed message? "
            "3) Check for cross-chain replay — is chainId included in the hash? "
            "4) Check abi.encodePacked with multiple variable-length types — "
            "   this causes hash collisions. "
            "5) Check EIP-712 compliance. "
            "6) Check if depositWithPermit or similar functions are complete. "
            "Report missing nonce as HIGH, missing ecrecover check as HIGH."
        )
    },
]

RISK_THRESHOLDS = {
    "critical": 80,
    "high": 60,
    "medium": 35,
    "low": 10
}


async def run_audit_pipeline(
    contract_code: str,
    contract_name: str = "Contract"
) -> dict:
    start_time = time.time()
    all_findings = []
    agents_used = []

    print("\n" + "=" * 60)
    print(f"🚀 AUDIT PIPELINE v2.0 STARTED for: {contract_name}")
    print(f"   Contract size: {len(contract_code)} chars")
    print(f"   GROQ_API_KEY present: {bool(settings.GROQ_API_KEY)}")
    print(f"   GEMINI_API_KEY present: {bool(settings.GEMINI_API_KEY)}")
    print(f"   Agents configured: {len(AGENT_CONFIGS)}")
    print(f"   PDF enabled: {REPORTLAB_AVAILABLE}")
    print("=" * 60)

    # --- Dispatch all agents in parallel ---
    groq_tasks = []
    for agent in AGENT_CONFIGS:
        groq_tasks.append(
            run_groq_analysis(contract_code, agent["focus"], agent["name"])
        )

    print("📡 Dispatching all agents...")
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
                print(f"❌ Groq agent {AGENT_CONFIGS[i]['name']} error: {res}")
                continue
            if res and isinstance(res, list):
                all_findings.extend(res)
                agents_used.append(AGENT_CONFIGS[i]["name"])
                print(f"   ✅ {AGENT_CONFIGS[i]['name']}: {len(res)} findings")
            else:
                print(f"   ⚠️ {AGENT_CONFIGS[i]['name']}: 0 findings")
    else:
        print(f"❌ Groq gather failed: {groq_results}")

    # Collect Gemini findings
    if not isinstance(gemini_result, Exception) and isinstance(gemini_result, list):
        all_findings.extend(gemini_result)
        agents_used.append("gemini_agent")
        print(f"   ✅ gemini_agent: {len(gemini_result)} findings")
    else:
        print(f"   ⚠️ gemini_agent: 0 findings")

    # Collect Slither findings
    if not isinstance(slither_result, Exception) and isinstance(slither_result, list):
        all_findings.extend(slither_result)
        agents_used.append("slither_agent")
        print(f"   ✅ slither_agent: {len(slither_result)} findings")
    else:
        print(f"   ⚠️ slither_agent: 0 findings (not installed or error)")

    # ═══ v2.0 — DEDUPLICATION ENGINE ═══
    unique_findings = deduplicate_and_validate(all_findings, contract_code)

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
    summary += f"Found {len(unique_findings)} unique issues "
    summary += f"(after deduplication from {len(all_findings)} raw findings): "
    summary += f"{counts['critical']} critical, {counts['high']} high, "
    summary += f"{counts['medium']} medium, {counts['low']} low."

    result = {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "total_findings": len(unique_findings),
        "raw_findings_count": len(all_findings),
        "critical_count": counts["critical"],
        "high_count": counts["high"],
        "medium_count": counts["medium"],
        "low_count": counts["low"],
        "info_count": counts["info"],
        "findings": unique_findings,
        "summary": summary,
        "agents_used": agents_used,
        "scan_duration_ms": scan_duration,
    }

    # ═══ v2.0 — PDF GENERATION ═══
    if REPORTLAB_AVAILABLE and settings.PDF_ENABLED:
        try:
            print("📄 Generating PDF report...")
            pdf_bytes = generate_audit_pdf(result)
            if pdf_bytes:
                result["pdf_base64"] = pdf_to_base64(pdf_bytes)
                result["pdf_available"] = True
                print(f"✅ PDF generated: {len(pdf_bytes)} bytes")
            else:
                result["pdf_available"] = False
        except Exception as e:
            print(f"❌ PDF generation error: {e}")
            result["pdf_available"] = False
    else:
        result["pdf_available"] = False

    print("\n" + "=" * 60)
    print(f"📊 AUDIT COMPLETE: {summary}")
    print(f"   Risk: {risk_level} (score: {risk_score})")
    print(f"   Duration: {scan_duration}ms")
    print(f"   Agents used: {agents_used}")
    print(f"   PDF: {'generated' if result.get('pdf_available') else 'not available'}")
    print("=" * 60 + "\n")

    return result
