# SentinelAI dashboard user guide

Use the [five-minute walkthrough](demo-walkthrough.md) for startup and login instructions. The sign-in account is a SentinelAI application user created with `scripts.create_user`; there is no default password.

## Primary workflow

1. **Dashboard** shows stored transaction counts, actionable alerts, active investigations and cases awaiting review. Expand **Explore demo** for five stored synthetic scenarios.
2. **Alerts** is a severity-first inbox with readable accounts, amounts, dates, review status and **Investigate**. Search activity and filter status/severity. Demonstration rules are explicitly distinguished from model-threshold alerts.
3. **Investigations** opens a case workspace containing linked payments, model factors, prior sender history, connected accounts, supporting evidence, report progress and human decisions. Repeated Investigate actions reuse the case. No UUID entry is needed.
4. **Transactions** searches account/payment references, filters payment type and paginates newest activity first. Open a payment for its full context. Account-history links apply the relevant account filter automatically.

## Investigation workspace

Choose a linked payment to inspect its amount, sender, recipient and actual model assessment. History uses strictly earlier simulation hours. Connected accounts include the inspected hour, using the backend's exclusive cutoff at the next hour. Select accounts with graph nodes or keyboard-accessible buttons; bounded results disclose truncation. Expand recorded money paths for transfer evidence.

Save connected accounts/history and add notes under **Supporting evidence**. Source IDs and JSON snapshots are inside **Technical details**. Start AI investigation to display progress and the report inline. The default **Mock AI report** is explicitly labeled and separate from genuine XGBoost inference.

Approve, reject or request a revision after reviewing findings, uncertainties and source citations. Report approval does not resolve a case. A senior analyst/admin separately records a decision and rationale, confirms it, and resolves the case. Analysts can inspect decisions but cannot record one.

## Advanced and accessibility

**Advanced / Admin** retains account profiles, network exploration, case administration, system status and the admin-only audit log. On small screens open the navigation menu; Escape closes it. Use the skip link to reach the main content. The header supports light/dark themes and sign-out. Expired sessions return to login.

Amounts are synthetic units, not an identified currency. Dates use the browser timezone. Structural patterns and model outputs do not prove crime. The PaySim model is not calibrated to the generated demonstration distribution; the default batch produced no model-threshold alerts.

See [verification status](frontend-qa.md) for current passed checks and outstanding live-browser verification.
