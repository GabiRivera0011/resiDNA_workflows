# IT Handoff Checklist — resiDNA Streamlit App

A practical companion to [IT_Deployment_Guide.md](IT_Deployment_Guide.md): exactly what to package up and send to IT, what to leave out, and who owns each remaining gap before this goes live on company infrastructure.

## 1. Code to hand over

Zip these up, keeping the folder structure intact — `app/` and `Scripts/` must stay siblings inside the zip (not flattened), since `app.py` locates `Scripts/` via a path relative to its own location (`sys.path.insert(0, ... / "Scripts")`), and imports `qpcr.py` / `plotting.py` directly. Missing either one crashes the app on the very first import, before the page loads.

- [ ] `app/app.py` — the Streamlit entry point
- [ ] `app/requirements.txt` — its dependencies, pinned to the exact versions tested
- [ ] `Scripts/qpcr.py` — classification/suitability logic `app.py` imports from
- [ ] `Scripts/plotting.py` — `style_table()` and formatting helpers `app.py` imports from
- [ ] `.streamlit/config.toml` — theme/layout config; only takes effect when Streamlit is launched from the directory that contains it, so it needs to travel with the app and IT needs to launch from that same relative location
- [ ] `IT_Deployment_Guide.md` — the deployment guide itself, so IT has the hosting-path decisions and hardening steps in hand
- [ ] `tests/` *(optional)* — lets IT verify the app behaves correctly once it's running in their environment (`pytest tests -v`)

## 2. Decisions you make before handoff

- [ ] **Hosting path** — Option A (on-prem/local server) or Option B (Azure + SharePoint embed)? See [IT_Deployment_Guide.md](IT_Deployment_Guide.md) for the tradeoffs.
- [ ] **Logging/audit policy** — the app keeps zero record of who ran what or what was uploaded (by design, for privacy). Decide whether your compliance process requires an audit trail — if so, that has to be designed and added; it doesn't exist today.

## 3. What IT builds around the code

- [ ] **Persistent service** — a `systemd` unit or Docker restart policy (Linux), or an NSSM-wrapped service / Task Scheduler entry (Windows). Today, closing the terminal or rebooting stops the app.
- [ ] **Reverse proxy + TLS** — Nginx, IIS, or the company's existing load balancer, terminating TLS with a company-issued certificate and sitting between users and the raw Streamlit process.
- [ ] **Authentication** — the app has none built in. Add `st.login()` with an `[auth]` block in `.streamlit/secrets.toml` (OpenID Connect against Microsoft Entra ID, so employees use their existing company login), or an auth proxy (e.g. oauth2-proxy) in front of the app if IT prefers to keep auth entirely outside the app code. **`secrets.toml` holds credentials — keep it out of whatever copy of these files ends up in version control.**
- [ ] **Network restriction** — bind to an internal DNS name/IP only, gated by firewall rules or VPN-only access. No public inbound port.
- [ ] **CSP header** *(Option B / SharePoint embed only)* — SharePoint Online blocks framing from arbitrary origins by default. The app's hosting config needs a `Content-Security-Policy: frame-ancestors` header explicitly allowlisting `https://yourtenant.sharepoint.com`. No Entra ID or SharePoint-side setting bypasses this — it's granted by the app's own host.
