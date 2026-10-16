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

## v18.0.18.0.0 - Branch stock filter + Stock Requests
- Sale order lines only offer products the order's Deduction Branch can supply
  (services/consumables + storable products with free stock there).
  `sale.order._get_stock_branch()` decides which branch is used.
- **Request Stock** button on the quotation -> `sale.stock.request` (product, qty, note).
- Inventory Managers (`stock.group_stock_manager`) get a To-Do + toast and a worklist at
  Inventory > Operations > Branch Stock Requests. They answer **We will proceed to Internal
  Transfer** or **Not Available**, optionally link the Internal Transfer, and later mark it received.
- The salesperson gets the answer in the chatter, as a To-Do and a toast, and follows it under
  Sales > Orders > My Stock Requests or the order's Stock Requests smart button.
- Once the transfer is validated, the product has free stock in the branch and shows up in the line filter.

## v18.0.19.0.0 - Multi-product requests + Start Internal Transfer
- "Request Stock" button next to Close on the "Product not available" warning
  (static/src/js/stock_warning_request.js).
- A request has product lines (`sale.stock.request.line`). Opened from an order it is pre-filled:
  missing products (missing qty), else the order's storable products, else empty.
- Inventory Manager button **Start Internal Transfer** answers the request, creates the draft
  Internal Transfer (source = other warehouse with the most stock, destination = requesting
  branch, Contact = the requesting salesperson) and opens it.
- Validating that transfer sets the request to Done; cancelling it re-opens the request.
- Migration 18.0.19.0.0 moves the old single product of each request into a line.

## v18.0.20.0.0 - Approve with payment journal + file preview
- Approve now opens a popup where the accountant picks the bank/cash journal the payment went to
  (`sale.order.payment.proof.approve.wizard`). It is stored on the proof (`payment_journal_id`).
- The invoice's Pay dialog (`account.payment.register`) preselects that journal (most recently
  approved proof of the order wins); the user can still change it.
- Payment Proof and Client ID files get an eye icon that opens them in an in-app viewer
  (images and PDFs) without downloading; download links stay. Works in the order's proof list,
  the Payment Proofs to Review list/form, the invoice's Payment Proofs tab and the Approve popup.

## v18.0.21.0.0 - fixes
- Preview/download icons were written as self-closing `<i/>` tags, which HTML does not close: the
  eye leaked into the next link (two eyes). Icons are now closed properly.
- Pay dialog: the proof's journal is now set in `default_get` (a default is not overwritten by the
  computed journal); the computed-journal override stays as a backup.
