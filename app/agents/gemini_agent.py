import json
import google.generativeai as genai
from app.config import settings

_configured = False


def configure():
    global _configured
    if not _configured and settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


# v2.0 — MASSIVELY improved prompt covering ALL vulnerability categories
# specifically targeting categories that v1 missed
PROMPT = """\
You are a world-class smart contract security auditor conducting a comprehensive audit.

Analyze this Solidity contract for ALL vulnerability types. You MUST check every single function.

MANDATORY VULNERABILITY CHECKLIST — check ALL of these:

1. REENTRANCY: Check every function with external calls. Is CEI (Checks-Effects-Interactions) pattern followed? Are state updates AFTER external calls?
2. ACCESS CONTROL: Check every function — does it have proper onlyOwner/role checks? Can anyone call critical functions like pause/unpause?
3. INTEGER MATH: Are unchecked blocks used? Can overflow/underflow occur?
4. SELFDESTRUCT/DELEGATECALL BACKDOORS: Does the contract have selfdestruct()? Does it have delegatecall to arbitrary addresses? These are CRITICAL rug-pull vectors.
5. SIGNATURE VERIFICATION: If ecrecover is used — is there a nonce? Is chainId included? Is the zero-address check done on the recovered address?
6. ERC20 SAFETY: Does transferFrom check return value? Are fee-on-transfer tokens handled? Is SafeERC20 used?
7. ORACLE MANIPULATION: Are price oracles validated? Is there staleness checking? Are price bounds enforced?
8. SHARE PRICE MANIPULATION: Can the first depositor manipulate share price? Can shares round to zero?
9. FLASH LOAN: Is the flash loan repayment check correct? Can it be bypassed via selfdestruct ETH donation?
10. GOVERNANCE: Is there a quorum requirement? Can proposals execute arbitrary calls? Is voting power snapshot-based?
11. FEE VALIDATION: Can fees be set above 100%? Are there upper bounds?
12. WITHDRAWAL DELAY: Is the delay meaningful or set to 0? Can it be set to infinity by owner?
13. ACCOUNTING: Do all deposit/withdraw paths update totalDeposited consistently?
14. DOS: Are there unbounded loops? Can external call failures block other users?
15. FUND LOCKING: Can user tokens/ETH get permanently locked?
16. INITIALIZATION: Can initialize() be called multiple times? Can anyone call it?
17. UNUSED VARIABLES: Are there declared-but-unused state variables (e.g., pendingOwner)?
18. TWO-STEP OWNERSHIP: Is ownership transfer single-step (dangerous) or two-step (safe)?

IMPORTANT RULES:
- Do NOT report tx.origin issues unless tx.origin is actually used in the code
- Do NOT report "msg.sender is insecure" — that is not a real vulnerability
- DO report selfdestruct and delegatecall backdoors as CRITICAL
- DO report missing signature replay protection as HIGH
- DO report unsafe ERC20 transfer (no return value check) as HIGH
- Each finding must reference the exact function name
- Do NOT repeat the same finding multiple times

Return ONLY a JSON array. No text outside JSON. No markdown backticks.

Each finding:
{
  "type": "Vulnerability Name",
  "severity": "critical|high|medium|low|info",
  "line": "line number or range",
  "function": "function_name",
  "description": "Detailed explanation with exact exploit path",
  "recommendation": "Specific fix with code suggestion"
}

Contract to audit:
```solidity
CONTRACT_CODE
```"""


async def run_gemini_analysis(contract_code: str) -> list:
    if not settings.GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY is empty — skipping Gemini agent")
        return []

    try:
        configure()

        model = genai.GenerativeModel(
            settings.GEMINI_MODEL,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=settings.GEMINI_MAX_TOKENS
            )
        )

        prompt = PROMPT.replace("CONTRACT_CODE",
                                contract_code[:15000])

        print("🔍 Gemini agent: sending request...")
        response = await model.generate_content_async(prompt)
        content = response.text.strip()
        print(f"🔍 Gemini agent: got response ({len(content)} chars)")

        try:
            parsed = json.loads(content)
            findings = []
            
            if isinstance(parsed, list):
                findings = parsed
            elif isinstance(parsed, dict):
                for key in ["findings", "vulnerabilities", "issues"]:
                    if key in parsed and isinstance(parsed[key], list):
                        findings = parsed[key]
                        break

            # v2.0 — Validate and tag findings
            validated = []
            for f in findings:
                if not isinstance(f, dict):
                    continue
                if not f.get("type") or not f.get("severity"):
                    continue
                sev = f.get("severity", "info").lower().strip()
                if sev not in ("critical", "high", "medium", "low", "info"):
                    sev = "info"
                f["severity"] = sev
                f["line"] = str(f.get("line", ""))
                f["source"] = "gemini_agent"
                validated.append(f)

            print(f"✅ Gemini agent: found {len(validated)} valid findings")
            return validated

        except json.JSONDecodeError:
            start = content.find('[')
            end = content.rfind(']') + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
                print(f"✅ Gemini agent: extracted {len(result)} findings from text")
                return result

        print("⚠️ Gemini agent: could not parse response as findings")
        return []

    except Exception as e:
        print(f"❌ Gemini agent error: {e}")
        return []
