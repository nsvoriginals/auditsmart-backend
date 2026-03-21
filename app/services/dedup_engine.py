"""
AuditSmart v2.0 — Finding Deduplication & Validation Engine

This is the KEY upgrade. It:
1. Removes duplicate findings (same root cause reported by multiple agents)
2. Filters known false positives (tx.origin when not used, generic msg.sender)
3. Normalizes severity classifications
4. Merges findings from the same root cause into one with richer description
"""

import re
from typing import List, Dict

# ═══════════════════════════════════════════
# FALSE POSITIVE PATTERNS — reject these
# ═══════════════════════════════════════════
FALSE_POSITIVE_PATTERNS = [
    # tx.origin reported when not actually used
    {
        "check": lambda f, code: (
            "tx.origin" in f.get("type", "").lower() or
            "tx.origin" in f.get("description", "").lower()
        ) and "tx.origin" not in code,
        "reason": "tx.origin not used in contract"
    },
    # Generic "msg.sender is insecure" — not a real vulnerability
    {
        "check": lambda f, code: (
            f.get("type", "").lower() in [
                "insecure use of msg.sender",
                "insecure msg.sender",
                "unsecured use of msg.sender"
            ]
        ),
        "reason": "msg.sender is standard Solidity authentication"
    },
    # "Unchecked math" reported generically without specific location
    {
        "check": lambda f, code: (
            f.get("type", "").lower() in [
                "insecure use of unchecked math",
                "unchecked math usage"
            ] and not f.get("line")
        ),
        "reason": "Generic unchecked math without specific location"
    },
]

# ═══════════════════════════════════════════
# SEVERITY UPGRADE RULES — catch misclassified severities
# ═══════════════════════════════════════════
SEVERITY_UPGRADES = [
    # setPaused with no access control = CRITICAL not medium
    {
        "check": lambda f: (
            "unprotected" in f.get("type", "").lower() and
            ("pause" in f.get("description", "").lower() or
             "pause" in f.get("function", "").lower())
        ),
        "new_severity": "critical",
        "reason": "Unprotected pause/unpause allows anyone to freeze/unfreeze contract"
    },
    # selfdestruct = always CRITICAL
    {
        "check": lambda f: "selfdestruct" in f.get("description", "").lower(),
        "new_severity": "critical",
        "reason": "selfdestruct can drain all contract funds"
    },
    # delegatecall to arbitrary address = CRITICAL
    {
        "check": lambda f: (
            "delegatecall" in f.get("description", "").lower() and
            ("arbitrary" in f.get("description", "").lower() or
             "any" in f.get("description", "").lower())
        ),
        "new_severity": "critical",
        "reason": "Arbitrary delegatecall can overwrite storage and steal funds"
    },
    # Reentrancy with ETH transfer = HIGH minimum
    {
        "check": lambda f: (
            "reentrancy" in f.get("type", "").lower() and
            f.get("severity") in ("medium", "low", "info")
        ),
        "new_severity": "high",
        "reason": "Reentrancy with external calls is minimum HIGH severity"
    },
]

# ═══════════════════════════════════════════
# SIMILARITY GROUPS — findings that should be merged
# ═══════════════════════════════════════════
SIMILARITY_KEYWORDS = {
    "reentrancy": ["reentrancy", "reentrant", "re-entrancy", "cross-function reentrancy"],
    "overflow": ["overflow", "underflow", "arithmetic", "unchecked math", "integer overflow", "integer underflow"],
    "oracle": ["oracle", "price manipulation", "price feed", "price oracle"],
    "access_control": ["access control", "unprotected", "unauthorized", "missing modifier", "anyone can call"],
    "dos": ["denial of service", "dos", "unbounded loop", "gas griefing", "gas limit"],
    "initialization": ["initialize", "initializ", "re-init", "multiple init"],
    "flash_loan": ["flash loan", "flashloan"],
    "signature": ["signature", "ecrecover", "replay", "nonce", "chainid"],
    "erc20": ["erc20", "transferfrom", "safe transfer", "return value", "fee-on-transfer"],
    "selfdestruct": ["selfdestruct", "self-destruct", "self destruct"],
    "delegatecall": ["delegatecall", "delegate call"],
    "governance": ["governance", "proposal", "voting", "quorum", "vote"],
}


def _classify_finding(finding: Dict) -> str:
    """Classify a finding into a similarity group."""
    text = (
        finding.get("type", "") + " " +
        finding.get("description", "")
    ).lower()
    
    for group, keywords in SIMILARITY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return group
    return "other"


def _get_dedup_key(finding: Dict) -> str:
    """Generate a deduplication key for a finding."""
    group = _classify_finding(finding)
    line = str(finding.get("line", "")).strip()
    func = finding.get("function", "").strip().lower()
    
    # For same group + same function = likely duplicate
    if func:
        return f"{group}::{func}"
    # For same group + same line range = likely duplicate
    if line:
        # Normalize line to nearest 10 to catch close matches
        try:
            line_num = int(re.search(r'\d+', line).group())
            line_bucket = (line_num // 20) * 20  # bucket by 20 lines
            return f"{group}::{line_bucket}"
        except (AttributeError, ValueError):
            pass
    
    return f"{group}::general"


def _severity_rank(sev: str) -> int:
    """Rank severity for comparison."""
    ranks = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
    return ranks.get(sev.lower(), 0)


def deduplicate_and_validate(
    findings: List[Dict],
    contract_code: str
) -> List[Dict]:
    """
    Main deduplication pipeline:
    1. Filter false positives
    2. Normalize severities
    3. Deduplicate by root cause
    4. Sort by severity
    """
    print(f"\n🔧 Dedup engine: processing {len(findings)} raw findings...")
    
    # Step 1: Filter false positives
    valid_findings = []
    fp_count = 0
    for f in findings:
        is_fp = False
        for pattern in FALSE_POSITIVE_PATTERNS:
            if pattern["check"](f, contract_code):
                print(f"   ❌ FALSE POSITIVE removed: {f.get('type', 'unknown')} — {pattern['reason']}")
                is_fp = True
                fp_count += 1
                break
        if not is_fp:
            valid_findings.append(f)
    
    print(f"   Removed {fp_count} false positives, {len(valid_findings)} remaining")
    
    # Step 2: Apply severity upgrades
    upgrade_count = 0
    for f in valid_findings:
        for rule in SEVERITY_UPGRADES:
            if rule["check"](f):
                old_sev = f["severity"]
                if _severity_rank(rule["new_severity"]) > _severity_rank(old_sev):
                    f["severity"] = rule["new_severity"]
                    print(f"   ⬆️ Severity upgrade: {f.get('type', '')} {old_sev} → {rule['new_severity']}")
                    upgrade_count += 1
                break
    
    print(f"   Applied {upgrade_count} severity upgrades")
    
    # Step 3: Deduplicate by root cause
    dedup_groups: Dict[str, List[Dict]] = {}
    for f in valid_findings:
        key = _get_dedup_key(f)
        if key not in dedup_groups:
            dedup_groups[key] = []
        dedup_groups[key].append(f)
    
    # Merge each group — keep the highest severity, longest description
    merged = []
    for key, group in dedup_groups.items():
        if len(group) == 1:
            merged.append(group[0])
            continue
        
        # Pick the best finding from the group
        group.sort(key=lambda x: (
            _severity_rank(x.get("severity", "info")),
            len(x.get("description", "")),
            len(x.get("recommendation", ""))
        ), reverse=True)
        
        best = group[0].copy()
        
        # Enrich description if multiple agents found it
        sources = list(set(f.get("source", "") for f in group if f.get("source")))
        if len(sources) > 1:
            best["confirmed_by"] = sources
            best["confidence"] = "high"  # Multiple agents agree
        else:
            best["confidence"] = "medium"
        
        merged.append(best)
        if len(group) > 1:
            print(f"   🔀 Merged {len(group)} findings into: {best.get('type', '')} [{key}]")
    
    # Step 4: Sort by severity
    merged.sort(key=lambda x: _severity_rank(x.get("severity", "info")), reverse=True)
    
    print(f"   ✅ Dedup complete: {len(findings)} raw → {len(merged)} unique findings")
    print(f"      (removed {fp_count} FPs, merged {len(findings) - fp_count - len(merged)} duplicates)\n")
    
    return merged
