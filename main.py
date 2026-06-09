import os
import time
import json
import asyncio
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Devin Agent Automation Server")

# Config validation
DEVIN_API_KEY = os.getenv("DEVIN_API_KEY")
DEVIN_ORG_ID = os.getenv("DEVIN_ORG_ID")
GITHUB_PAT = os.getenv("GITHUB_PAT")
GITHUB_REPO = os.getenv("GITHUB_REPO")

JOBS_FILE = "jobs.json"

def init_db():
    if not os.path.exists(JOBS_FILE):
        with open(JOBS_FILE, "w") as f:
            json.dump({}, f)

init_db()

def get_jobs():
    with open(JOBS_FILE, "r") as f:
        return json.load(f)

def save_job(issue_number, data):
    jobs = get_jobs()
    jobs[str(issue_number)] = data
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=4)

# --- Devin & GitHub API Core Orchestration ---

def check_github_and_trigger_devin():
    """Polls GitHub for issues with the target label and spins up Devin sessions."""
    print("🤖 Checking GitHub for new issues...")
    init_db()
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues?state=open&labels=devin-remediate"
    headers = {"Authorization": f"token {GITHUB_PAT}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"❌ Failed to fetch GitHub issues: {response.text}")
            return
            
        issues = response.json()
        jobs = get_jobs()
        
        for issue in issues:
            issue_num = str(issue["number"])
            
            # If we haven't processed this issue yet, spawn Devin!
            if issue_num not in jobs:
                print(f"🔥 Found new issue #{issue_num}: {issue['title']}. Triggering Devin...")
                
                devin_prompt = f"""
You are an expert platform and security engineer. Please fix GitHub Issue #{issue_num} in our repository.
Repository to clone and work out of: https://github.com/{GITHUB_REPO}

Issue Context:
Title: {issue['title']}
Description: {issue['body']}

Instructions:
1. Clone the repository fork.
2. Locate where the cryptography dependency is specified (e.g. in requirements files, setups, etc.).
3. Upgrade its version to 41.0.6 or higher to resolve the security CVE.
4. Verify code consistency and that dependencies lock properly.
5. Create a new branch named 'fix/cryptography-vulnerability-issue-{issue_num}'.
6. Push your branch changes and open a Pull Request directly back into our fork.
"""
                
                # Call Devin v3 API to create a session
                devin_url = f"https://api.devin.ai/v3/organizations/{DEVIN_ORG_ID}/sessions"
                devin_headers = {
                    "Authorization": f"Bearer {DEVIN_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "prompt": devin_prompt,
                    "idempotency_key": f"github-issue-{issue_num}"
                }
                
                devin_resp = requests.post(devin_url, json=payload, headers=devin_headers)
                
                if devin_resp.status_code in [200, 201]:
                    devin_data = devin_resp.json()
                    session_id = devin_data.get("session_id")
                    
                    if not session_id:
                        print(f"❌ API responded successfully but session_id was missing! Response: {devin_data}")
                        continue
                    
                    # Track this active automation job
                    save_job(issue_num, {
                        "issue_title": issue['title'],
                        "session_id": session_id,
                        "status": "running",
                        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "devin_url": f"https://app.devin.ai/sessions/{session_id}"
                    })
                    print(f"✅ Devin Session successfully initialized: {session_id}")
                else:
                    print(f"❌ Failed to spin up Devin session. Status Code: {devin_resp.status_code}")
                    print(f"🚨 API Error Payload Response: {devin_resp.text}")
                    
    except Exception as e:
        print(f"🚨 Error during polling loop execution: {str(e)}")

def update_active_session_statuses():
    """Queries Devin v3 API to refresh status records for tracking analytics."""
    jobs = get_jobs()
    headers = {"Authorization": f"Bearer {DEVIN_API_KEY}"}
    
    for issue_num, job_info in jobs.items():
        if job_info["session_id"] == "None" or not job_info["session_id"]:
            continue
            
        if job_info["status"] in ["running", "blocked_on_user", "new"]:
            session_id = job_info["session_id"]
            url = f"https://api.devin.ai/v3/organizations/{DEVIN_ORG_ID}/sessions/{session_id}"
            
            try:
                resp = requests.get(url, headers=headers)
                if resp.status_code == 200:
                    status_data = resp.json()
                    current_state = status_data.get("status", "running")
                    
                    job_info["status"] = current_state
                    job_info["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    save_job(issue_num, job_info)
                    print(f"🔄 Session {session_id} status updated: {current_state}")
            except Exception as e:
                print(f"⚠️ Failed status refresh for session {session_id}: {e}")

async def polling_scheduler():
    """Asynchronous infinite loop acting as our cron engine inside Docker."""
    while True:
        check_github_and_trigger_devin()
        update_active_session_statuses()
        await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(polling_scheduler())

# --- Observability Interface Engine ---

@app.get("/", response_class=HTMLResponse)
def dashboard():
    """An elegant executive analytical summary dashboard answering 'How do I know this is working?'"""
    jobs = get_jobs()
    
    total = len(jobs)
    active = sum(1 for j in jobs.values() if j["status"] in ["running", "blocked_on_user", "new"])
    completed = sum(1 for j in jobs.values() if j["status"] == "completed")
    failed = sum(1 for j in jobs.values() if j["status"] in ["failed", "stopped"])
    
    rows_html = ""
    for issue_num, details in jobs.items():
        status_value = details["status"].upper()
        status_color = "#3498db" if details["status"] in ["running", "new"] else "#2ecc71" if details["status"] == "completed" else "#e74c3c"
        rows_html += f"""
        <tr>
            <td style="padding:12px; border-bottom:1px solid #ddd;"><b>#{issue_num}</b></td>
            <td style="padding:12px; border-bottom:1px solid #ddd;">{details["issue_title"]}</td>
            <td style="padding:12px; border-bottom:1px solid #ddd;"><span style="background:{status_color}; color:white; padding:4px 8px; border-radius:4px; font-size:12px;">{status_value}</span></td>
            <td style="padding:12px; border-bottom:1px solid #ddd; font-family:monospace; font-size:12px;">{details["session_id"]}</td>
            <td style="padding:12px; border-bottom:1px solid #ddd;">{details["started_at"]}</td>
            <td style="padding:12px; border-bottom:1px solid #ddd;"><a href="{details["devin_url"]}" target="_blank" style="color:#2980b9; text-decoration:none; font-weight:bold;">View Mission ↗</a></td>
        </tr>
        """
        
    html_content = f"""
    <html>
        <head>
            <title>Devin Autonomous Remediation Center</title>
            <meta http-equiv="refresh" content="10">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 40px; background: #f9f9f9; color: #333; }}
                .container {{ max-width: 1100px; margin: auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
                .metrics {{ display: flex; gap: 20px; margin-bottom: 30px; }}
                .card {{ flex: 1; background: #f1f2f6; padding: 20px; border-radius: 6px; text-align: center; border-left: 5px solid #2f3542; }}
                .card.active {{ border-left-color: #3498db; }}
                .card.success {{ border-left-color: #2ecc71; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background: #2f3542; color: white; text-align: left; padding: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>📊 Devin Autonomous Agent Fleet Analytics</h2>
                <p style="color:#7f8c8d;">Engineering Leadership Operational Visibility Center. Updates automatically every 10 seconds.</p>
                
                <div class="metrics">
                    <div class="card"><h3>Total Dispatched</h3><p style="font-size:24px; font-weight:bold; margin:5px 0;">{total}</p></div>
                    <div class="card active"><h3>Active Missions</h3><p style="font-size:24px; font-weight:bold; color:#3498db; margin:5px 0;">{active}</p></div>
                    <div class="card success"><h3>Autonomously Resolved</h3><p style="font-size:24px; font-weight:bold; color:#2ecc71; margin:5px 0;">{completed}</p></div>
                    <div class="card" style="border-left-color:#e74c3c;"><h3>Failures Blocked</h3><p style="font-size:24px; font-weight:bold; color:#e74c3c; margin:5px 0;">{failed}</p></div>
                </div>

                <h3>📋 Task Remediation Ledger</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Issue ID</th>
                            <th>Target Task Objective</th>
                            <th>Fleet Status</th>
                            <th>Devin Session UUID</th>
                            <th>Dispatched Timestamp</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html if rows_html else '<tr><td colspan="6" style="padding:20px; text-align:center; color:#95a5a6;">Scanning GitHub for flagged issues... apply the "devin-remediate" label to get started!</td></tr>'}
                    </tbody>
                </table>
            </div>
        </body>
    </html>
    """
    return html_content