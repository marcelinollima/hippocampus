---
name: orders-report-mismatch
description: "The sales dashboard and the monthly report disagree per salesperson. Cause found; fix still to be decided with finance."
metadata:
  type: project
  modified: 2026-03-12T16:20:00Z
  status: pending
  status_at: 2026-03-12T16:20:00Z
---

## Cause (proved)

The dashboard credits an order to whoever **closed** it (`order_events.user_id`),
the report to whoever **created** it (`orders.created_by`).

## Still pending

Finance must decide which rule is correct before we change either side.
Data lives in [[shop-api-db-access]].
