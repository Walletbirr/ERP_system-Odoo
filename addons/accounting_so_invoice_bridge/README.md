# Accounting - Create Invoice from Sales Order (v18.0.14.2.0)

Sales -> Accounting workflow with Payment Proof approval.

## Flow (v15.1: approval BEFORE invoice)
1. Salesperson confirms the quotation.
2. Salesperson attaches **payment proof + client ID** and presses **Submit**
   (credit payment terms skip the proof).
3. **Notification 1 -> Accounting**: To-Do on the order + toast; the proof appears in
   Accounting > Customers > **Payment Proofs to Review**.
4. Accountant downloads the files and **Approves** or **Rejects** (reason required).
   Rejected: To-Do back to the salesperson, who fixes and **Resubmits** (Accounting is notified again).
5. When all proofs are Approved: **notification -> Salesperson**, and only now the
   **Create Invoice** button appears (server-side check in `_create_invoices` too).
6. Draft invoice created. **Notification 2 -> Accounting**: confirm it after checking the accounting setup.
   Only Accounting can confirm.
7. Salesperson can open the invoice (smart button / right after Create Invoice) on a
   **read-only sales view**: no accounts, journal items, balance, journal or chatter.

## Setup
- Tick the group **"Accountant: Approve Payment Proof & Confirm Sales Invoices"** on each
  accountant (same group as the old "Can Create Invoice from Sales Order", renamed).
- Upgrade runs a migration: open quotations (draft/sent, not pending approval) stop requiring
  manager approval. Orders already "Pending Approval" are left for the manager to finish.

## Proof statuses
Pending -> Awaiting Approval -> Approved | Rejected -> (Resubmit) -> Awaiting Approval.
Status fields are protected server-side; submitted/approved files can't be edited or deleted.

## Enforced server-side
- Invoice creation needs a Submitted/Approved proof (non-credit, non-sudo).
- `account.move._post` on invoices from Sales Orders: Accounting group / Settings Admin only,
  and proofs must be Approved (non-credit). Cron/sudo flows are not restricted.
- `action_confirm` re-checks that Selling Prices are balanced (custom_sale_management),
  since the manager approval no longer does.

## Menu
Accounting > Customers > **Sales Invoices to Confirm**: draft invoices created from orders, with
their payment-proof status. (The old "Create Invoice from Sales Order" menu was removed.)

## What Sales sees (older notes; superseded by step 7: the Invoices button is back, on the read-only view)
Salespeople never land on the invoice page: after **Create Invoice** they stay on the order and get
"Invoice sent to Accounting"; the order's **Invoices** smart button is hidden for them, and the
**Balance** button on invoices is accountant-only. Native Odoo already hides Journal Items, the
Account column and Confirm / Register Payment / Cancel from non-accounting users.
Read access on invoices remains (Sales needs it for invoiced quantities), so a direct URL would still
open the invoice read-only: no edit, no confirm.
