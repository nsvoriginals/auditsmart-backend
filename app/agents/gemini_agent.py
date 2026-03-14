import json
import google.generativeai as genai
from app.config import settings

_configured = False

def configure():
    global _configured
    if not _configured and settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True

PROMPT = """You are a senior smart contract security auditor. 
Perform a comprehensive security audit on this Solidity contract.
Look for ALL vulnerability types including but not limited to:
reentrancy, access control, integer overflow/underflow, 
front-running, flash loan attacks, oracle manipulation,
timestamp dependence, tx.origin misuse, delegatecall issues.

Return ONLY a JSON array of findings. Each finding:
{
  "type": "vulnerability name",
  "severity": "critical|high|medium|low|info",
  "line": "line number or range",
  "description": "detailed explanation",
  "recommendation": "specific fix"
}

Contract:
```solidity
CONTRACT_CODE
```"""

async def run_gemini_analysis(contract_code: str) -> list:
    if not settings.GEMINI_API_KEY:
        return []

    try:
        configure()
        model = genai.GenerativeModel(
            'gemini-1.5-pro',
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=4096
            )
        )

        prompt = PROMPT.replace("CONTRACT_CODE", contract_code[:12000])

        response = await model.generate_content_async(prompt)
        content = response.text.strip()

        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in ["findings", "vulnerabilities", "issues"]:
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
        except json.JSONDecodeError:
            start = content.find('[')
            end = content.rfind(']') + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])

        return []

    except Exception as e:
        print(f"Gemini agent error: {e}")
        return []
