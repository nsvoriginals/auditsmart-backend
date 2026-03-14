import asyncio
import json
import tempfile
import os
import subprocess

async def run_slither_analysis(contract_code: str) -> list:
    """Run Slither static analysis on the contract."""
    try:
        # Check if slither is available
        result = subprocess.run(['which', 'slither'], capture_output=True)
        if result.returncode != 0:
            print("Slither not installed, skipping")
            return []

        # Write contract to temp file
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sol', delete=False
        ) as f:
            f.write(contract_code)
            tmp_path = f.name

        try:
            # Run slither with JSON output
            proc = await asyncio.create_subprocess_exec(
                'slither', tmp_path,
                '--json', '-',
                '--solc-disable-warnings',
                '--exclude-dependencies',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if not stdout:
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

                # Get line info
                elements = detector.get("elements", [])
                line = ""
                if elements:
                    src = elements[0].get("source_mapping", {})
                    lines = src.get("lines", [])
                    if lines:
                        line = str(lines[0])

                findings.append({
                    "type": detector.get("check", "unknown"),
                    "severity": severity,
                    "line": line,
                    "description": detector.get("description", "").strip(),
                    "recommendation": "Review Slither documentation for this detector.",
                    "source": "slither"
                })

            return findings

        finally:
            os.unlink(tmp_path)

    except asyncio.TimeoutError:
        print("Slither timed out")
        return []
    except Exception as e:
        print(f"Slither error: {e}")
        return []
