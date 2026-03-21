import json
import asyncio
from groq import AsyncGroq
from app.config import settings

client = None


def get_client():
    global client
    if client is None:
        if not settings.GROQ_API_KEY:
            return None
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return client


# v2.0 — Much more specific system prompt that forces structured output
# and eliminates common false positives
SYSTEM_PROMPT = """\
You are an expert Solidity smart contract security auditor with 10+ years experience.
You audit contracts for real vulnerabilities that can be exploited, NOT theoretical concerns.

CRITICAL RULES:
1. Only report vulnerabilities that ACTUALLY EXIST in the code.
2. Do NOT report tx.origin issues if tx.origin is never used.
3. Do NOT report generic "msg.sender is insecure" — msg.sender is the standard way to authenticate.
4. Each finding MUST reference a specific function name and explain the exact exploit path.
5. Do NOT duplicate findings — if you already reported reentrancy in withdraw(), don't report it again.
6. Severity must be accurate:
   - critical = direct fund theft, total contract compromise
   - high = significant fund loss, privilege escalation
   - medium = limited fund risk, logic errors
   - low = best practice violations, gas issues
   - info = code quality, style issues

Respond ONLY with a valid JSON array. No text outside JSON. No markdown.

Each finding must have exactly these fields:
{
  "type": "Specific Vulnerability Name",
  "severity": "critical|high|medium|low|info",
  "line": number or "range like 150-160",
  "function": "function_name_or_modifier",
  "description": "Exact explanation of what is wrong and HOW to exploit it",
  "recommendation": "Specific code fix, not generic advice"
}
"""


async def run_groq_analysis(contract_code: str, focus: str, agent_name: str) -> list:
    if not settings.GROQ_API_KEY:
        print(f"⚠️ GROQ_API_KEY is empty — skipping {agent_name}")
        return []

    groq_client = get_client()
    if not groq_client:
        print(f"⚠️ Groq client not initialized — skipping {agent_name}")
        return []

    try:
        prompt = f"""Audit this Solidity contract. Focus SPECIFICALLY on: {focus}

IMPORTANT: Only report issues you can see in the actual code. Reference exact function names.
If a function has a nonReentrant modifier, do NOT report reentrancy for that function.
If the code never uses tx.origin, do NOT report tx.origin issues.

Solidity contract to audit:
```solidity
{contract_code[:10000]}
```

Return ONLY a JSON array of findings. Be precise and specific."""

        print(f"🔍 Groq {agent_name}: sending request (focus: {focus[:50]}...)")

        response = await asyncio.wait_for(
            groq_client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=settings.GROQ_MAX_TOKENS,
                temperature=settings.GROQ_TEMPERATURE,
                response_format={"type": "json_object"}
            ),
            timeout=settings.AGENT_TIMEOUT_SECONDS
        )

        content = response.choices[0].message.content.strip()
        print(f"🔍 Groq {agent_name}: got response ({len(content)} chars)")

        try:
            parsed = json.loads(content)

            # Handle both array and {findings: [...]} formats
            if isinstance(parsed, list):
                findings = parsed
            elif isinstance(parsed, dict):
                for key in ["findings", "vulnerabilities", "issues", "results"]:
                    if key in parsed and isinstance(parsed[key], list):
                        findings = parsed[key]
                        break
                else:
                    findings = []
            else:
                findings = []

            # v2.0 — Validate each finding has required fields
            validated = []
            for f in findings:
                if not isinstance(f, dict):
                    continue
                if not f.get("type") or not f.get("severity"):
                    continue
                # Normalize severity
                sev = f.get("severity", "info").lower().strip()
                if sev not in ("critical", "high", "medium", "low", "info"):
                    sev = "info"
                f["severity"] = sev
                # Ensure line is string
                f["line"] = str(f.get("line", ""))
                # Add source tag
                f["source"] = agent_name
                validated.append(f)

            print(f"✅ Groq {agent_name}: found {len(validated)} valid findings")
            return validated

        except json.JSONDecodeError:
            start = content.find('[')
            end = content.rfind(']') + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
                print(f"✅ Groq {agent_name}: extracted {len(result)} findings")
                return result
            print(f"⚠️ Groq {agent_name}: could not parse response")
            return []

    except asyncio.TimeoutError:
        print(f"⚠️ Groq {agent_name}: timed out after {settings.AGENT_TIMEOUT_SECONDS}s")
        return []
    except Exception as e:
        print(f"❌ Groq {agent_name} error: {e}")
        return []
