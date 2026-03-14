# AuditSmart Backend — Railway Deployment Guide

## Step 1: GitHub pe push karo
```bash
cd auditsmart-backend
git init
git add .
git commit -m "Initial AuditSmart backend"
git remote add origin https://github.com/YOUR_USERNAME/auditsmart-backend.git
git push -u origin main
```

## Step 2: Railway pe deploy karo
1. railway.app pe jao → Login
2. "New Project" → "Deploy from GitHub repo"
3. `auditsmart-backend` select karo
4. Railway auto-detect karega Procfile

## Step 3: MongoDB add karo
1. Railway project mein → "+ New" → "Database" → "MongoDB"
2. MongoDB connect hone ke baad:
   Variables tab → `MONGODB_URL` automatically set ho jaega

## Step 4: Environment Variables set karo
Railway project → "Variables" tab mein yeh sab add karo:

| Variable | Value |
|----------|-------|
| JWT_SECRET | (random 32+ char string) |
| GROQ_API_KEY | console.groq.com se |
| GEMINI_API_KEY | aistudio.google.com se |
| RAZORPAY_KEY_ID | razorpay dashboard se |
| RAZORPAY_KEY_SECRET | razorpay dashboard se |
| FRONTEND_URL | https://auditsmart.org |

## Step 5: Domain milega
Railway → Settings → Networking → "Generate Domain"
Kuch aisa milega: `auditsmart-backend-production.up.railway.app`

## Step 6: Frontend mein URL set karo
auditsmart-defi.html mein line 1:
```javascript
var BACKEND_URL = 'https://auditsmart-backend-production.up.railway.app';
```
