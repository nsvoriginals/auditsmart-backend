import json
import asyncio
from groq import AsyncGroq
from app.config import settings

client = None

def get_client():
    global client
    if client is None:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return client

SYSTEM_PROMPT = """You are an expert smart contract security auditor. 
Analyze the provided Solidity code for vulnerabilities.
Respond ONLY with a valid JSON array of findings. No explanation text outside JSON.
Each finding must have:
- type: string (vulnerability name)
- severity: "critical" | "high" | "medium" | "low" | "info"
- line: string or number (approximate line)
- description: string (what the bug is)
- recommendation: string (how to fix it)

If no vulnerabilities found, return empty array [].
"""

async def run_groq_analysis(contract_code: str, focus: str, agent_name: str) -> list:
    if not settings.GROQ_API_KEY:
        return []

    prompt = f"""Focus specifically on: {focus}

Solidity contract to audit:
```solidity
{contract_code[:8000]}
```

Return JSON array of findings related to {focus} only."""

    try:
        cl = get_client()
        # Stagger requests to avoid rate limits
        await asyncio.sleep(0.3)

        response = await cl.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content.strip()

        # Parse JSON
        try:
            parsed = json.loads(content)
            # Handle both array and {findings: [...]} formats
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in ["findings", "vulnerabilities", "issues", "results"]:
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
            return []
        except json.JSONDecodeError:
            # Try to extract array from response
            start = content.find('[')
            end = content.rfind(']') + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            return []

    except Exception as e:
        print(f"Groq {agent_name} error: {e}")
        return []
