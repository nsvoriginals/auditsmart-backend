import asyncio
import json
import tempfile
import os
import subprocess


async def run_slither_analysis(contract_code: str) -> list:
    """Run Slither static analysis on the contract."""
    try:
        result = subprocess.run(['which', 'slither'],
                                capture_output=True)
        if result.returncode != 0:
            print("⚠️ Slither not installed — skipping static analysis")
            return []

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sol', delete=False
        ) as f:
            f.write(contract_code)
            tmp_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                'slither', tmp_path,
                '--json', '-',
                '--solc-disable-warnings',
                '--exclude-dependencies',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=60)

            if not stdout:
                print("⚠️ Slither: no output")
                return []

            data = json.loads(stdout.decode())
            findings = []

            for detector in data.get("results", {}).get("detectors", []):
                impact = detector.get("impact", "Informational").lower()
                severity_map = {
                    "high": "high",
                    "medium": "medium",
                    "low": "low",
                    "informational": "info",
                    "optimization": "info"
                }
                severity = severity_map.get(impact, "info")

                elements = detector.get("elements", [])
                line = ""
                func_name = ""
                if elements:
                    src = elements[0].get("source_mapping", {})
                    lines = src.get("lines", [])
                    if lines:
                        line = str(lines[0])
                    func_name = elements[0].get("name", "")

                findings.append({
                    "type": detector.get("check", "unknown"),
                    "severity": severity,
                    "line": line,
                    "function": func_name,
                    "description": detector.get("description", "").strip(),
                    "recommendation": "Review Slither documentation for this detector.",
                    "source": "slither_agent"
                })

            print(f"✅ Slither: found {len(findings)} findings")
            return findings

        finally:
            os.unlink(tmp_path)

    except asyncio.TimeoutError:
        print("⚠️ Slither timed out")
        return []
    except Exception as e:
        print(f"❌ Slither error: {e}")
        return []
