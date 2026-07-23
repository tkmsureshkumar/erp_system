# IRONLINE ACCESS ERP — User Guide
**CTO Logistics & Infra · Fleet Operations System**
Version 2.0 | July 2026

---

## Table of Contents
1. [Overview](#1-overview)
2. [User Roles](#2-user-roles)
3. [Logging In](#3-logging-in)
4. [Navigation](#4-navigation)
5. [Document Lifecycle](#5-document-lifecycle)
6. [Masters — Machines, Customers, Sites](#6-masters--machines-customers-sites)
7. [Work Orders](#7-work-orders)
8. [Deployments](#8-deployments)
9. [Machine Movements](#9-machine-movements)
10. [Work Logs](#10-work-logs)
11. [Invoice Generation](#11-invoice-generation)
12. [Approval Workflow — Edit Requests](#12-approval-workflow--edit-requests)
13. [Admin Panel](#13-admin-panel)
14. [Reports](#14-reports)
15. [Quick Reference — Permissions Table](#15-quick-reference--permissions-table)

---

## 1. Overview

IRONLINE ACCESS ERP is the fleet operations system for CTO Logistics & Infra. It manages:
- Machine and equipment master records
- Customer and site onboarding
- Work Orders and deployments
- Monthly work logs (billing basis)
- Invoice generation
- Complete audit trail and approval workflow

The system runs in a web browser. No software installation is required.

---

## 2. User Roles

The system has two roles:

### Admin (Ayush)
- Full access to every page and every record
- Can create, edit, and delete any record
- Can lock and unlock records directly
- Approves or rejects staff edit requests
- Manages user accounts and permissions
- Views the complete audit and activity history

### Staff
- Creates and manages day-to-day records
- Can add and edit Machines, Customers, Sites, Work Orders, Movements, Work Logs
- Can generate and print Invoices directly (no approval needed)
- Can view assigned reports
- **Cannot** delete records (deactivation only)
- **Cannot** mark machines as Sold or Scrapped
- Must request Admin approval to edit locked/finalized records

---

## 3. Logging In

1. Open the ERP URL in your browser (Chrome or Edge recommended).
2. Enter your **Email Address** and **Password**.
3. Click **Sign In**.
4. Your session stays active for 7 days. You will be automatically signed back in if you close and reopen the browser.

**Forgot password?** Contact Admin (Ayush) to reset your password from the Admin panel.

**Sign Out:** Click your name in the top-right corner → click **Sign out**.

---

## 4. Navigation

The left sidebar contains all pages organised into three sections:

| Section | Pages |
|---------|-------|
| **OPERATIONS** | Dashboard, Customers, Sites, Operators, Machines, Assets, Machine Move, Work Orders, Close WO, Deployments, Invoice, Worklog |
| **REPORTS** | Active Dep, Fleet Status, Fleet Util, Mach History, WL Report, WO Report, WL Status, Cust Report, Op Report |
| **CONFIG** | System |

> **Note for Staff:** You will only see the pages that Admin has granted access to. If a page is missing, ask Admin to update your permissions.

The **top bar** shows your current location (breadcrumb) and your name. For Admin users, the bell icon 🔔 shows the number of pending edit requests with a red badge.

---

## 5. Document Lifecycle

Every transactional record (Work Order, Movement, Work Log) follows a three-stage lifecycle:

```
  DRAFT  →  (Submit & Lock)  →  LOCKED  →  (Request Edit + Admin Approval)  →  UNLOCKED  →  (Save)  →  LOCKED
```

| Status | Who can edit | Meaning |
|--------|-------------|---------|
| **Draft** | Anyone with access | Record is new or in progress. Freely editable. |
| **Locked** | Admin only (directly) | Record is finalised. Staff must request approval to edit. |
| **Unlocked** | Staff who requested + Admin | Admin has approved an edit request. Staff can make changes. Record auto-relocks on save. |
| **Cancelled** | Admin only | Record has been cancelled (soft-deleted). |

**Status chips** appear next to every record name in lists and detail panels so you can see the current state at a glance.

Master records (Machines, Customers, Sites) use a simpler two-state system: **Active** or **Inactive**.

---

## 6. Masters — Machines, Customers, Sites

### Adding a New Record
1. Navigate to **Machines** (or Customers / Sites) in the sidebar.
2. Click the **+ New** button in the top-right of the list panel.
3. Fill in all required fields (marked with *).
4. Click **Save**.
5. The record is immediately live and **Active**.

### Editing a Record
1. Click the record in the list to open its detail panel.
2. Edit any field directly — the form is always editable for active master records.
3. Click **Update** to save.

### Deactivating a Record (Soft Delete)
Records are never permanently deleted by Staff. Instead:
1. Open the record detail panel.
2. Scroll to the bottom of the form.
3. Click **⛔ Deactivate**.
4. The record status changes to **Inactive** and it disappears from working lists.
5. The data is preserved in the database.

> **Admin only:** Re-activate an inactive record by selecting "Show Inactive" in the list, opening the record, and clicking **✅ Re-activate**.

### Machines — Additional Restrictions for Staff
- Staff **cannot** set `Operational Status` to **Sold** or **Scrapped**. Only Admin can mark a machine with these statuses.
- The deactivate button is visible to both Staff and Admin.

---

## 7. Work Orders

### Creating a Work Order
1. Go to **Work Orders** in the sidebar.
2. Click **+ New Work Order**.
3. Select Customer and Site.
4. Set Start Date (and optionally End Date).
5. Enter the Client WO Number if provided by the customer.
6. In the **Machine Config** section, add each machine:
   - Select machine from dropdown
   - Set Billing Type, Rental/Month, shift hours, working days, OT rate
7. Click **Save Work Order**.
8. The WO is created in **Draft** status.

### Locking a Work Order
When a Work Order is finalised and should not be further edited:
1. Open the Work Order.
2. Scroll to the bottom of the form.
3. Click **📤 Submit & Lock** (Staff) or **🔒 Lock Record** (Admin).
4. The status changes to **Locked** and the form becomes read-only.

### Editing a Locked Work Order (Staff)
1. Open the locked Work Order.
2. You will see the record in read-only mode with a blue locked banner.
3. Click **✏️ Request Edit from Admin** to expand the request form.
4. Type a clear reason explaining why the edit is needed.
5. Click **Submit Request**.
6. Admin will receive a notification and review your request.
7. Once approved, the WO will show as **Unlocked** — you can then edit and save. It relocks automatically on save.

### Closing a Work Order
1. Go to **Close WO** in the sidebar.
2. Select the Work Order to close.
3. Confirm the closure. The system automatically:
   - Sets the WO status to Closed
   - Sets `Billing End Date = today` for all machines that are On Rent (billing started, no end date set)

---

## 8. Deployments

1. Go to **Deployments** in the sidebar.
2. Select a Work Order.
3. For each machine, set:
   - **Billing Start Date (BSD)**: the date billing began
   - **Billing End Date (BED)**: the date billing ended (leave blank if still active)
4. Save the deployment. Machine status updates automatically:
   - No BSD → **Reserved**
   - BSD set, no BED → **On Rent** (billing active)
   - Both BSD and BED set → **Available**

---

## 9. Machine Movements

Machine movements track physical movement of equipment (Load → Transit → Unload).

### Creating a Movement
1. Go to **Machine Move** in the sidebar.
2. Select the machine.
3. Choose the Movement Type: **Load**, **Transit**, or **Unload**.
4. Fill in From/To locations and movement date.
5. Click **Save Movement**.

### Locking a Movement
Same pattern as Work Orders:
- **Staff:** Click **📤 Submit & Lock** when the movement record is final.
- **Locked:** Click **✏️ Request Edit from Admin** to request changes.

---

## 10. Work Logs

Work Logs are the basis for billing. They track daily shift data for each machine on a Work Order.

### Creating / Saving a Work Log
1. Go to **Worklog** in the sidebar.
2. Select Work Order, Machine, and Billing Month.
3. Enter shift data in the schedule table (Start/End times, breaks, OT hours).
4. Click **Save Draft** to save progress without locking.
5. When the month's data is complete, click **Submit** to finalise (locks the work log).

### Editing a Submitted Work Log (Staff)
Submitted work logs are **Locked**. To edit:
1. Open the work log.
2. Click **✏️ Request Edit from Admin**.
3. Enter your reason.
4. Submit the request.
5. Admin approves → the log is unlocked and you can edit and resubmit.

---

## 11. Invoice Generation

Staff can generate invoices **without any approval**.

### Generating an Invoice
1. Go to **Invoice** in the sidebar.
2. Select the **Customer** and **Work Order**.
3. In the left panel, expand each machine and tick the charges to include:
   - Completed Work Logs (Hiring charges)
   - Mobilisation / Demobilisation (if applicable)
4. In **Invoice Configuration**:
   - Enter the Invoice Number (format: `BL/CLI/YY-YY/NNN`, e.g. `BL/CLI/26-27/204`)
   - Set the Invoice Date
   - Choose GST type: **CGST/SGST** (intra-state) or **IGST** (inter-state)
   - Optionally add HSN/SAC code and Notes
5. The **Invoice Preview** on the right updates automatically.
6. Click **⬇ Download Invoice (HTML)** to save the invoice file.
7. Open the downloaded HTML file in Chrome → press **Ctrl+P** → choose **Save as PDF** or **Print**.
8. Click **🧾 Generate Invoice** to save the invoice record to the system.

> **Duplicate check:** The system prevents saving an invoice with a number that already exists.

---

## 12. Approval Workflow — Edit Requests

### Staff: How to Request an Edit
1. Open the locked record (Work Order, Movement, or Work Log).
2. At the bottom of the page, click **✏️ Request Edit from Admin**.
3. Type a clear, specific reason for the change.
4. Click **Submit Request**.
5. You will see a confirmation message. Admin is notified via the red badge on the notification bell (🔔) in the top bar.
6. Wait for approval. The page will show **Unlocked** when approved.
7. Make your edits and click **Save / Update**. The record automatically relocks.

### Admin: How to Approve or Reject Requests
1. Click the 🔔 notification bell in the top bar (or go to **Admin Panel**).
2. Open the **Requests** tab. Pending requests show a count badge.
3. For each request, review the record type, label, requester name, and reason.
4. Click **✅ Approve** to unlock the record for editing.
   - The target record's status changes to **Unlocked**.
   - The requesting staff member can now make changes.
5. Click **❌ Reject** to deny the request.
   - An optional rejection note can be added.
   - The record remains Locked. Staff is expected to check the status.

---

## 13. Admin Panel

Accessible only to Admin role. Go to **Admin** in the bottom of the left sidebar.

### Tab 1 — Users
- **Add New User:** Enter name, email, password, role (User/Admin), and page access.
- **Edit Permissions:** Expand any user card to change role, page access, or deactivate the account.

> Page access controls which sidebar pages a Staff user can see. Admin users always see everything regardless of page access settings.

### Tab 2 — Activity Log
- Full searchable log of all system actions.
- Filter by: Module, Action type, Date range, User name.
- Includes: Create, Update, Delete (soft), Login, Logout, User management, Approvals.

### Tab 3 — Requests
- Lists all Edit/Delete requests across the system.
- Filter by status: Pending / Approved / Rejected.
- Filter by record type: Work Order / Movement / Work Log.
- Approve or Reject with optional notes.

---

## 14. Reports

All reports are read-only. They do not modify any data.

| Report | Description |
|--------|-------------|
| **Active Dep** | Currently deployed machines by site |
| **Fleet Status** | Status of all machines (Available, On Rent, Reserved, etc.) |
| **Fleet Util** | Utilisation percentage per machine over time |
| **Mach History** | Complete history of a selected machine |
| **WL Report** | Worklog detail for a selected Work Order / Machine / Month |
| **WO Report** | Work Order summary with billing totals |
| **WL Status** | Which worklogs are Draft vs Submitted vs Missing |
| **Cust Report** | All Work Orders and deployments for a customer |
| **Op Report** | Operator assignment history |

---

## 15. Quick Reference — Permissions Table

| Action | Staff | Admin |
|--------|-------|-------|
| View Dashboard & Reports | ✅ (if granted) | ✅ |
| Add Machine / Customer / Site | ✅ | ✅ |
| Edit Machine / Customer / Site | ✅ | ✅ |
| Deactivate Master Record | ✅ | ✅ |
| Re-activate Master Record | ❌ | ✅ |
| Mark Machine as Sold/Scrapped | ❌ | ✅ |
| Create Work Order | ✅ | ✅ |
| Edit Draft Work Order | ✅ | ✅ |
| Submit & Lock Work Order | ✅ | ✅ |
| Edit Locked Work Order | ❌ (request needed) | ✅ (direct) |
| Create Machine Movement | ✅ | ✅ |
| Create / Save Work Log Draft | ✅ | ✅ |
| Submit Work Log | ✅ | ✅ |
| Edit Locked Work Log | ❌ (request needed) | ✅ (direct) |
| Generate Invoice | ✅ | ✅ |
| Submit Edit Request | ✅ | N/A |
| Approve / Reject Edit Request | ❌ | ✅ |
| Manage Users | ❌ | ✅ |
| View Activity Log | ❌ | ✅ |
| View Edit Requests | ❌ | ✅ |

---

## Support

For access issues, password resets, or questions about the system, contact:
**Admin — Ayush**

For software bugs or feature requests, contact the development team.

---

*IRONLINE ACCESS ERP · CTO Logistics & Infra · Confidential*
