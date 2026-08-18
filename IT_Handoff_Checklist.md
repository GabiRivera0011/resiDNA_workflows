# IT Handoff Checklist — resiDNA Streamlit App

A practical companion to [IT_Deployment_Guide.md](IT_Deployment_Guide.md): exactly what to package up and send to IT, what to leave out, and who owns each remaining gap before this goes live on company infrastructure. For the actual step-by-step execution once IT has this package, see [IT_Setup_Guide_OptionA.md](IT_Setup_Guide_OptionA.md) — Option A (on-prem/local server) is the decided path.

## 1. Code to hand over

Zip these up, keeping the folder structure intact — `app/` and `Scripts/` must stay siblings inside the zip (not flattened), since `app.py` locates `Scripts/` via a path relative to its own location (`sys.path.insert(0, ... / "Scripts")`), and imports `qpcr.py` / `plotting.py` directly. Missing either one crashes the app on the very first import, before the page loads.

- [ ] `app/app.py` — the Streamlit entry point
- [ ] `app/audit_log.py` — the opt-in audit log `app.py` calls on each PDF download; see section 2 below
- [ ] `app/requirements.txt` — its dependencies, pinned to the exact versions tested
- [ ] `Scripts/qpcr.py` — classification/suitability logic `app.py` imports from
- [ ] `Scripts/plotting.py` — `style_table()` and formatting helpers `app.py` imports from
- [ ] `app/assets/logo.png` *(optional)* — PDF report header logo; the report falls back to a plain placeholder box if this file isn't present
- [ ] `.streamlit/config.toml` — theme/layout config; only takes effect when Streamlit is launched from the directory that contains it, so it needs to travel with the app and IT needs to launch from that same relative location
- [ ] `IT_Deployment_Guide.md` — the deployment guide itself, so IT has the hosting-path decisions and hardening steps in hand
- [ ] `IT_Setup_Guide_OptionA.md` — the from-scratch runbook IT actually executes from: real commands, service files, and config templates
- [ ] `tests/` *(optional)* — lets IT verify the app behaves correctly once it's running in their environment (`pytest tests -v`)

## 2. Decisions made before handoff

- [x] **Hosting path** — **Option A (on-prem/local server)**, decided. See [IT_Deployment_Guide.md](IT_Deployment_Guide.md) for the tradeoffs that were weighed, and [IT_Setup_Guide_OptionA.md](IT_Setup_Guide_OptionA.md) for the concrete build steps.
- [x] **Logging/audit policy** — compliance confirmed an audit trail is required. Two remaining pieces, worth keeping straight for the *next* gap like this one:
  1. **The logging code itself** — application logic, so it's part of the code handoff (section 1), not something IT builds. Written: `app/audit_log.py`, wired into `app/app.py`'s PDF download button. It records who generated a report and what was uploaded (timestamp, filename, a hash of it, assay/run info, submitter/reviewer name, pass/fail) — never the actual analytical results.
  2. **Where it's stored and for how long** — IT's infrastructure job, same category as the persistent service or reverse proxy below. See section 3.

## 3. What IT builds around the code

- [ ] **Persistent service** — a `systemd` unit or Docker restart policy (Linux), or an NSSM-wrapped service / Task Scheduler entry (Windows). Today, closing the terminal or rebooting stops the app.
- [ ] **Enable the audit log** — set the `RESIDNA_AUDIT_LOG` environment variable on the server process (it's off unless set — see item 2 above). Also set up retention/rotation for `Logs/audit.log` per whatever period compliance specified, and make sure it's covered by this server's backup routine. Exact config: [IT_Setup_Guide_OptionA.md](IT_Setup_Guide_OptionA.md) steps 4–6.
- [ ] **Reverse proxy + TLS** — Nginx, IIS, or the company's existing load balancer, terminating TLS with a company-issued certificate and sitting between users and the raw Streamlit process.
- [ ] **Authentication** — the app has none built in. Add `st.login()` with an `[auth]` block in `.streamlit/secrets.toml` (OpenID Connect against Microsoft Entra ID, so employees use their existing company login), or an auth proxy (e.g. oauth2-proxy) in front of the app if IT prefers to keep auth entirely outside the app code. **`secrets.toml` holds credentials — keep it out of whatever copy of these files ends up in version control.**
- [ ] **Network restriction** — bind to an internal DNS name/IP only, gated by firewall rules or VPN-only access. No public inbound port.
- [ ] **CSP header** *(Option B / SharePoint embed only — not applicable to the decided Option A path)* — SharePoint Online blocks framing from arbitrary origins by default. The app's hosting config needs a `Content-Security-Policy: frame-ancestors` header explicitly allowlisting `https://yourtenant.sharepoint.com`. No Entra ID or SharePoint-side setting bypasses this — it's granted by the app's own host.
