# AuditSmart v2.0 — Upgrade & Deployment Guide

## What Changed (v1.0 → v2.0)

### New Files Added
| File | Purpose |
|------|---------|
| `app/services/dedup_engine.py` | **NEW** — Deduplication + false positive filtering |
| `app/services/pdf_generator.py` | **NEW** — PDF audit report generation |
| `app/services/__init__.py` | Package init |

### Files Modified
| File | Changes |
|------|---------|
| `app/agents/pipeline.py` | 8 agents (was 6), dedup integration, PDF generation |
| `app/agents/groq_agent.py` | Better prompts, false positive prevention, timeout handling |
| `app/agents/gemini_agent.py` | 18-point checklist prompt, covers all vuln categories |
| `app/routes/audit.py` | PDF download endpoints, better validation |
| `app/routes/dashboard.py` | Enhanced stats (raw vs deduped counts) |
| `app/routes/payment.py` | Fixed body param model, added /plans endpoint |
| `app/main.py` | Version bump to 2.0.0 |
| `app/config.py` | New settings for PDF, agent config, timeouts |
| `app/database.py` | Added index creation on startup |
| `requirements.txt` | Added `reportlab==4.1.0` |

### Unchanged Files
- `app/utils/auth.py` — Already solid, no changes needed
- `app/agents/slither_agent.py` — Already solid, minor source tag added
- `Procfile` — Same
- `railway.toml` — Same

---

## Key New Features

### 1. Deduplication Engine
- Removes false positives (tx.origin when not used, generic msg.sender warnings)
- Auto-corrects severity (e.g., unprotected pause → CRITICAL)
- Merges duplicate findings from multiple agents by root cause
- Tracks confidence level (high = multiple agents agree)

### 2. PDF Report Generation
- Professional branded PDF reports
- Available in FREE tier
- Download via API: `GET /audit/report/{audit_id}/pdf`
- Base64 via API: `GET /audit/report/{audit_id}/pdf-data`
- Stored in MongoDB with audit document

### 3. Two New Specialist Agents
- `backdoor_agent` — Detects selfdestruct, delegatecall, arbitrary governance execution
- `signature_agent` — Detects missing nonce, chainId, ecrecover zero-address checks

### 4. Enhanced Agent Prompts
All agent prompts rewritten to:
- Require function-level specificity
- Prevent known false positives
- Cover previously missed vulnerability categories
- Force structured JSON output with validation

---

## Deployment Steps (Railway)

### Step 1: Replace the codebase
```bash
# In your Railway project directory
rm -rf app/ requirements.txt Procfile railway.toml
# Copy all files from this zip
cp -r auditsmart-v2/* .
```

### Step 2: Set environment variables
Same .env as before — no new env vars required. All new settings have defaults.

Optional new env vars:
```
PDF_ENABLED=true          # default: true
MAX_CONTRACT_SIZE=50000   # default: 50000
GROQ_MODEL=llama-3.3-70b-versatile  # default
AGENT_TIMEOUT_SECONDS=120 # default: 120
```

### Step 3: Deploy
```bash
# Railway auto-deploys on push
git add -A
git commit -m "Upgrade to AuditSmart v2.0 — dedup, PDF, enhanced agents"
git push
```

### Step 4: Verify
```bash
curl https://api.auditsmart.org/
# Should return: {"status":"AuditSmart API running","version":"2.0.0","features":[...]}

curl https://api.auditsmart.org/health
# Should return: {"status":"ok","version":"2.0.0"}
```

---

## New API Endpoints

### PDF Download (direct file)
```
GET /audit/report/{audit_id}/pdf
Authorization: Bearer {token}
Response: application/pdf file download
```

### PDF Base64 (for frontend rendering)
```
GET /audit/report/{audit_id}/pdf-data
Authorization: Bearer {token}
Response: {"pdf_base64": "...", "pdf_available": true}
```

### Plan Info (no auth)
```
GET /payment/plans
Response: {"plans": {"free": {...}, "pro": {...}, "enterprise": {...}}}
```

---

## Frontend Integration (for PDF download button)

Add this to the audit results page in the frontend:

```javascript
// PDF Download Button Handler
async function downloadPDF(auditId) {
    const token = localStorage.getItem('token');
    
    try {
        const response = await fetch(
            `${API_BASE}/audit/report/${auditId}/pdf`,
            {
                headers: { 'Authorization': `Bearer ${token}` }
            }
        );
        
        if (!response.ok) throw new Error('PDF not available');
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `AuditSmart_Report_${auditId}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    } catch (err) {
        console.error('PDF download failed:', err);
        alert('PDF not available. Please re-run the audit.');
    }
}
```

Add a button in the audit results UI:
```html
<button onclick="downloadPDF('AUDIT_ID_HERE')" class="btn-pdf">
    📄 Download PDF Report
</button>
```

---

## Scan Response Changes (v2.0)

The `/audit/scan` response now includes:
```json
{
    "id": "...",
    "risk_level": "critical",
    "risk_score": 100,
    "total_findings": 35,
    "raw_findings_count": 55,
    "critical_count": 10,
    "high_count": 15,
    "medium_count": 8,
    "low_count": 2,
    "info_count": 0,
    "findings": [
        {
            "type": "Selfdestruct Backdoor",
            "severity": "critical",
            "line": "350",
            "function": "migrateVault",
            "description": "...",
            "recommendation": "...",
            "source": "backdoor_agent",
            "confidence": "high",
            "confirmed_by": ["backdoor_agent", "gemini_agent"]
        }
    ],
    "summary": "...",
    "agents_used": ["reentrancy_agent", "...", "backdoor_agent", "signature_agent"],
    "scan_duration_ms": 45000,
    "pdf_available": true,
    "version": "2.0"
}
```

New fields:
- `raw_findings_count` — before deduplication
- `info_count` — informational findings
- `pdf_available` — whether PDF was generated
- `confidence` — per finding (high/medium)
- `confirmed_by` — which agents found this
- `function` — which function the vuln is in
- `source` — which agent reported this
- `version` — "2.0"

---

## Troubleshooting

### PDF not generating?
- Check Railway logs for: `⚠️ reportlab not installed`
- Fix: `pip install reportlab==4.1.0` (already in requirements.txt)
- Check: `PDF_ENABLED=true` in env (default is true)

### Agents timing out?
- Increase: `AGENT_TIMEOUT_SECONDS=180` in env
- Groq has rate limits — if all 8 agents hit at once, some may fail
- Pipeline handles this gracefully — partial results still returned

### Old audits don't have PDF?
- Only new audits (v2.0+) generate PDFs
- Old audits will show `pdf_available: false`
- User needs to re-run audit to get PDF

---

## File Structure
```
auditsmart-v2/
├── app/
│   ├── __init__.py
│   ├── config.py              # Settings with v2 additions
│   ├── database.py            # MongoDB with indexes
│   ├── main.py                # FastAPI app v2.0
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── groq_agent.py      # Enhanced prompts
│   │   ├── gemini_agent.py    # 18-point checklist
│   │   ├── slither_agent.py   # Static analysis
│   │   └── pipeline.py        # 8-agent orchestrator
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py            # Login/Register
│   │   ├── audit.py           # Scan + PDF endpoints
│   │   ├── dashboard.py       # Stats
│   │   └── payment.py         # Razorpay + Plans
│   ├── services/
│   │   ├── __init__.py
│   │   ├── dedup_engine.py    # NEW: Dedup + FP filter
│   │   └── pdf_generator.py   # NEW: PDF reports
│   └── utils/
│       ├── __init__.py
│       └── auth.py            # JWT + password
├── .env.example
├── .gitignore
├── DEPLOY.md
├── Procfile
├── railway.toml
└── requirements.txt
```
