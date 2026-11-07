# Five guided synthetic scenarios

Open **Dashboard → Explore demo**. Cards come from stored batch metadata and link to actual transactions/accounts; they do not contain fixture responses. Each card displays the genuine model score. **Explore scenario** opens payment context; **Investigate** opens or creates its case. A zero/low score does not invalidate the visible transaction pattern, and a high score would not prove crime.

| Scenario | Stored activity | What to inspect |
|---|---|---|
| A — Everyday payments | Everyday customer sends one modest payment daily to Local shop or Utility merchant. | Prior payment count and average, actual model factors, repeated recipients. No rule alert is created; a model alert would exist only if its real threshold were crossed. |
| B — A larger-than-usual transfer | Growing business has 63 days of modest supplier transfers before a 90,000-unit payment. | Compare the earlier average with the payment amount. The demonstration rule describes the deviation independently of the model result. |
| C — Many senders, one recipient | Ten customers transfer a total of 75,000 units to Collection account in one hour. | Collection account's ten senders, incoming edges and transfer amounts. The card centers the recipient automatically. |
| D — Funds move on quickly | Collection account sends six 7,000-unit transfers in the following hour. | Fan-in/fan-out metrics and the recorded transfer hours. Select Collection account and expand **Follow the money** to inspect paths. These records show temporal adjacency, not proof that particular incoming funds financed particular outgoing payments. |
| E — Connected transfer activity | Four named businesses make five connected transfers with a return path. | The prepared case links five alerts and transaction snapshots. Choose a linked payment, inspect connected accounts, save history/network evidence, and prepare the report. |

The eight demonstration alerts consist of one for B, one for C, one for D and five for E. Their type is `demo_rule_*` and the inbox labels them **Demonstration rule**. Model alerts are a separate `model_threshold` type with an independent score-based condition.

Scenario records and balances are reproducible for a given configuration. Database creation timestamps, analyst-created cases, reports and human review timestamps naturally vary. A changed generator recipe should use a fresh batch name or an intentional reset.
