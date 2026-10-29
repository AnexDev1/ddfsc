# DDFSC Quality Control Demo Presenter Guide

**A complete rehearsal script for the Saturday client demonstration**

Dire Dawa Food Complex ERP Implementation  
Version 1.0 | 28 October 2026

## Purpose of this guide

This guide prepares you to demonstrate the standalone Quality Control application from configuration through incoming wheat, flour release, finished goods release, non-conformance, reinspection, reporting, permissions, and audit history. It explains what to click, what to enter, what the audience should observe, which Jira requirement each feature addresses, and how the feature improves factory control.

**Important.** The acceptance limits used in the local database are demonstration values. Present them as workflow examples only. The factory Quality Manager must approve the real laboratory specifications before production use.

**Main message to deliver**

> Say: “Quality is now a controlled business process inside Odoo. Every governed batch is identified by lot, tested against a versioned plan, reviewed by an authorised manager, and prevented from leaving quarantine until it passes or a documented exception is approved.”

## How to use this document

Read Sections 1 through 5 before the meeting. During the live demo, follow Sections 6 through 13 in order. Sections 14 through 18 prepare you for questions, limitations, recovery, and rehearsal.

| Section | Use |
|---|---|
| 1 to 5 | Understand the design, terminology, Jira coverage, roles, and preparation. |
| 6 to 13 | Follow the live demo click by click. |
| 14 | Explain each Jira item without claiming unfinished scope. |
| 15 | Answer likely client questions. |
| 16 | Recover if data or navigation does not behave as expected. |
| 17 | Run a timed rehearsal. |
| 18 | Complete the final checklist before the meeting. |

### Recommended demo duration

| Segment | Minutes |
|---|---:|
| Introduction and architecture | 3 |
| Acceptance plans | 5 |
| Incoming wheat pass | 8 |
| Failure and NCR | 8 |
| Reinspection | 5 |
| Flour and finished goods | 7 |
| Reports, security, audit | 5 |
| Questions | 9 |

Target total: approximately 50 minutes. If the meeting is shorter, use the condensed route in Section 17.

# 1 Demo story and business outcome

The factory buys wheat, receives it into a controlled Wheat Receiving location, tests the batch, and releases only approved wheat to General Store. Milling produces flour into Flour Temp Finished, where QC must approve the flour before Flour Store can supply production departments. Pasta, bread, and biscuit production follows the same pattern: output enters a temporary finished location, QC reviews the finished lot, and only approved product reaches Finished Goods Store.

> Say: “I will show the same control principle at three factory checkpoints: incoming raw material, produced flour, and finished products. I will also show what happens when a result fails, how the system preserves history, and how management can report on quality performance.”

## What changed compared with the earlier flow

- Quality Control is a standalone application instead of being hidden under Manufacturing.
- QC checks are created against the lot automatically for controlled products.
- A test result and the manager release decision are separate steps.
- Controlled stock cannot leave Wheat Receiving or temporary finished locations before QC release.
- Failed mandatory tests place the lot on hold and create a non-conformance record.
- Reinspection preserves the original result snapshot instead of overwriting history.
- Plans have approval, versions, effective dates, and protection against editing approved standards.
- QC activities, overdue NCR reminders, pivot analysis, charts, and printable reports are available.

# 2 Solution architecture in plain language

| Layer | What it does | Why it matters |
|---|---|---|
| OCA Quality Control engine | Provides generic inspections, tests, questions, categories, and triggers. | Uses a maintained Community foundation instead of recreating every generic QC concept. |
| DDFSC Quality Management | Provides the standalone app, governed plans, lot review, NCR, reinspection, reporting, security, and notifications. | Matches the factory process and Jira business requirements. |
| DDFSC Manufacturing and Inventory | Creates plant locations, lots, production links, transfers, and stock validation gates. | Makes QC affect real inventory movement rather than acting as a separate checklist. |

> Say: “The generic inspection engine provides reusable quality concepts. The DDFSC module adds the factory-specific approval, quarantine, release, traceability, and non-conformance rules. Inventory enforces the decision at transfer validation.”

## Two screens that must not be confused

| Screen | Use |
|---|---|
| Quality Control > DDFSC Operations > QC Lots | Primary operational screen for DDFSC batch testing, approval, quarantine, release, and traceability. |
| Quality Control > Inspections | Generic OCA inspection records. Useful for future configurable triggers and inspection forms; the current DDFSC gate is driven mainly from QC Lots. |

# 3 Terms you should explain

| Term | Meaning |
|---|---|
| Lot or batch | The traceable identity of a received or produced quantity. QC results and decisions belong to this identity. |
| Checkpoint | Where QC is required: Incoming Wheat, Flour Release, or Finished Goods Release. |
| Acceptance plan | The governed set of required tests and limits for products at a checkpoint. |
| QC check | One required laboratory or observation result copied from the applicable plan onto a lot. |
| Inspection status | Data Entry, Awaiting Review, Approved, or Rejected. It describes the review workflow. |
| QC status or disposition | Pending, Passed, On Hold, Rejected, or Released by Exception. It controls stock movement. |
| NCR | Non-Conformance Report. It records a quality failure, its owner, cause, action, disposition, verification, and closure. |
| CAPA | Corrective and preventive action. In the current module these are controlled fields and stages inside the NCR. |
| Reinspection | A new attempt after investigation. Prior results are archived in Inspection History. |
| Release by exception | A manager-authorised release of held or rejected stock with a mandatory reason. |

# 4 Roles and separation of duties

| Role | Can do | Cannot do |
|---|---|---|
| DDFSC Quality User | Open QC lots, enter results, submit for review, and work with NCR records according to access. | Approve plans, make final inspection approval, close NCRs, or release exceptions. |
| DDFSC Quality Manager | Maintain and approve plans, review results, approve or reject inspections, close NCRs, and release exceptions. | Bypass mandatory data and recorded reasons. |
| Warehouse or Store User | Receive lots and validate transfers after release. | Move controlled pending, held, or rejected lots out of quarantine. |
| Production or Operation Manager | Complete manufacturing and view linked quality lots. | Override the QC gate unless also authorised as Quality Manager. |

> Say: “The module separates result entry from final approval. This supports segregation of duties: the inspector records evidence and the Quality Manager makes the disposition decision.”

# 5 Pre demo preparation

## 5.1 Prepare data one day before

1. **Confirm the local database is ddfsc.** Do not demonstrate from an unrelated demo database.
2. **Confirm the Quality Control application opens.** The menus should include DDFSC Operations, Inspections, and DDFSC Standards for a manager.
3. **Prepare two incoming wheat lots.** Use one for a passing path and one for a failing path. Record their numbers.
4. **Prepare one flour manufacturing order and one finished-product order.** Leave them where the finished lot exists in the temporary finished location.
5. **Confirm Administrator has DDFSC Quality Manager access.** Use a second ordinary QC user only if demonstrating role differences live.
6. **Open required tabs in advance.** Keep QC Lots, Acceptance Plans, Non-Conformances, and one receipt or production order available.
7. **Remove browser distractions.** Close developer tools, clear unrelated tabs, and use 90 to 100 percent zoom.
8. **Record backup references.** Know the purchase order, receipt, manufacturing order, and lot numbers used in rehearsal.

## 5.2 Values for the demonstration

| Checkpoint | Test | Demonstration rule | Passing value | Failing example |
|---|---|---|---:|---:|
| Incoming Wheat | Moisture | At most 13.5 percent | 12 | 15 |
| Incoming Wheat | Impurity | At most 2 percent | 1 | 3 |
| Incoming Wheat | Hectoliter weight | At least 76 kg/hl | 77 | 70 |
| Incoming Wheat | Wet gluten | At least 24 percent | 25 | 20 |
| Flour Release | Moisture | At most 14 percent | 13 | 15 |
| Flour Release | Wet gluten | At least 24 percent | 25 | 20 |
| Finished Goods | Organoleptic | Exactly 1 in current demo plan | 1 | 0 |
| Finished Goods | Actual to labelled weight ratio | Between 0.98 and 1.02 | 1.00 | 0.95 |

**Important.** These are demonstration workflow values from the current local setup, not approved factory specifications.

# 6 Open the standalone Quality Control workspace

1. **Click the app launcher and open Quality Control.**
2. **Point out DDFSC Operations.** It contains QC Lots, QC Reports, and Non-Conformances.
3. **Point out DDFSC Standards.** Quality Managers use Acceptance Plans here.
4. **Point out generic Inspections and Tests.** These come from the OCA inspection foundation.

> Say: “The client asked for Quality Control to be a standalone module. It now has its own application, security groups, operations, standards, inspections, non-conformances, and reporting. Users no longer need to search through manufacturing menus to find QC work.”

**Expected result.** The audience sees Quality Control as an independent workspace with DDFSC-specific operations and configuration.

**Jira coverage:** QC-03 module foundation, QC-18 operational workspace, and the architecture portion of QC-02.

# 7 Demonstrate governed acceptance plans

1. **Open Quality Control > DDFSC Standards > Acceptance Plans.**
2. **Open Incoming Wheat - DEMO limits.**
3. **Show checkpoint and products.** The plan applies to specific products at a factory checkpoint.
4. **Show version and effective dates.** An approved plan records its effective period, approver, and approval time.
5. **Show Required Tests.** Read Test, Acceptance Rule, lowest or highest acceptable value, unit, Mandatory, Result Type, and Required Range.
6. **Explain numeric and qualitative tests.** Numeric tests compare a number with limits. Qualitative tests compare an observation with allowed answers.
7. **Show Demo Specification warning.** The system blocks approval while this flag remains enabled.
8. **Explain approval locking.** Approved governed fields and test lines cannot be silently edited.
9. **Explain Create New Version.** A manager copies to a new draft, changes it, retires the old plan, and approves the new effective version.

> Say: “This update prevents laboratory standards from being changed without governance. Existing inspection history keeps the specification used at that time. New standards are introduced as a new version with an effective date.”

**Expected result.** The audience understands that a QC plan is a controlled standard rather than an editable spreadsheet.

**Jira coverage:** QC-04 inspection plans and part of QC-17 auditability.

## How results are calculated

- **At most:** pass when measured value is less than or equal to the maximum.
- **At least:** pass when measured value is greater than or equal to the minimum.
- **Between:** pass when inside both boundaries, including the boundary values.
- **Qualitative:** pass when the observation matches an allowed answer, ignoring case and surrounding spaces.
- A result remains Pending until Test Complete is selected or a qualitative observation is entered.
- A failed mandatory test causes manager review to reject the inspection and hold the lot.

# 8 Demonstrate incoming wheat passing QC

## 8.1 Receive the batch into quarantine

1. **Open Procurement and the prepared wheat purchase order.**
2. **Open the related receipt.**
3. **Confirm destination WH/Stock/Wheat Receiving.** This is quarantine; receipt does not mean unrestricted availability.
4. **Open Details on the Wheat line and assign a new lot.** Every controlled batch needs a traceable lot.
5. **Enter received quantity and complete store approval.**
6. **Validate the receipt.**

> Say: “The batch is physically received, but it enters Wheat Receiving rather than General Store. This records custody while keeping the wheat unavailable to production until QC releases it.”

**Expected result.** The receipt completes and the lot quantity is in Wheat Receiving with pending QC.

**Jira coverage:** QC-05, QC-11, and QC-15.

## 8.2 Enter laboratory results

1. **Open Quality Control > DDFSC Operations > QC Lots.**
2. **Search the new lot and open it.**
3. **Show Traceability.** Point out Source Receipt and Supplier. Production lots show Manufacturing Order.
4. **Confirm tests are already visible.** Do not use Refresh Tests in the normal flow; automatic preparation is part of the update.
5. **Enter Moisture 12 and mark Test Complete.**
6. **Enter Impurity 1 and mark Test Complete.**
7. **Enter Hectoliter weight 77 and mark Test Complete.**
8. **Enter Wet gluten 25 and mark Test Complete.**
9. **Point out immediate Pass badges.** Each result is evaluated against Required Range.

> Say: “The inspector enters only the measured result. The minimum, maximum, unit, required range, and pass or fail calculation come from the approved plan. This reduces guesswork and prevents users from changing acceptance limits during inspection.”

**Expected result.** All checks show Pass, but Inspection Status is still Data Entry and QC Status is Pending because final review has not occurred.

**Jira coverage:** QC-08 and part of QC-15.

## 8.3 Submit and approve

1. **Click Submit for QC Approval.**
2. **Explain validation.** Missing mandatory results prevent submission.
3. **Show Awaiting Review.** Submitted results are locked so they cannot change quietly.
4. **As Quality Manager click Approve / Reject Results.**
5. **Show Inspection Status Approved and QC Status Passed.**
6. **Point out submitter, reviewer, and timestamps.**

> Say: “The inspector and reviewer are recorded separately. Approval is based on completed mandatory tests. The decision, user, and timestamp form the electronic audit trail.”

**Expected result.** The lot becomes Passed and the manager review activity is completed.

**Jira coverage:** QC-10, QC-16, and QC-17.

## 8.4 Release to General Store

1. **Click Release Wheat to General Store.**
2. **Open or confirm the generated transfer.**
3. **Validate the transfer.**
4. **Return to the lot and show quantity in General Store.**

> Say: “Approval changes the lot from quarantined evidence to releasable inventory. The controlled transfer moves it to General Store, where the flour department can request it.”

**Expected result.** Approved wheat becomes available in General Store.

**Jira coverage:** QC-11.

# 9 Demonstrate failure and automatic non-conformance

## 9.1 Create the failure

1. **Open the second prepared wheat lot.**
2. **Enter Moisture 15.** This exceeds the current demo maximum of 13.5.
3. **Enter passing remaining values:** Impurity 1, Hectoliter 77, Wet gluten 25.
4. **Complete every test and submit.**
5. **As Quality Manager click Approve / Reject Results.**

> Say: “The manager button evaluates the evidence. Because one mandatory test failed, the system rejects the inspection rather than approving the batch.”

**Expected result.** Inspection Status is Rejected, QC Status is On Hold, and an NCR is created automatically.

**Jira coverage:** QC-08, QC-10, and QC-12.

## 9.2 Prove the stock gate

1. **Attempt to transfer the failed lot from Wheat Receiving to General Store.**
2. **Click Validate.**
3. **Read the blocking message and use Open QC Lot if offered.**

> Say: “The control is enforced inside inventory validation. A failed or pending lot cannot leave a controlled location merely because a user created a transfer.”

**Expected result.** Odoo blocks the transfer and routes the user to the QC lot.

**Jira coverage:** QC-11.

## 9.3 Show the NCR link

1. **Return to the failed lot.**
2. **Open Non-Conformances.**
3. **Open the generated NCR.**
4. **Point out lot, product, receipt, supplier, affected quantity, and failed-test description.**

> Say: “The non-conformance is not a disconnected note. It inherits the product, lot, supplier or manufacturing reference, quantity, and failed tests, preserving traceability to the original event.”

**Jira coverage:** QC-12 and QC-15.

# 10 Demonstrate NCR and CAPA workflow

1. **Set Severity.** Use Major unless the client specifies another classification.
2. **Assign Owner and Due Date.** The owner receives an activity; overdue records are identified and managers are reminded.
3. **Review Defect Description and click Start Investigation.**
4. **Enter Root Cause.** Example: “Incoming load had elevated moisture because the vehicle cover was damaged during rain.”
5. **Click Require Action.**
6. **Enter Corrective Action.** Example: “Isolate the batch and request supplier replacement or controlled re-drying assessment.”
7. **Enter Preventive Action.** Example: “Add vehicle-cover inspection and moisture pre-check before unloading.”
8. **Choose Disposition.** Select Additional Test / Reinspection for this demo.
9. **Click Send for Verification.** Corrective action is required first.
10. **Explain closure requirements.** A Quality Manager cannot close without disposition, verification, and closure note.

> Say: “Corrective action addresses this failure. Preventive action reduces recurrence. Verification proves the action was effective. Closure is a manager decision, not an automatic result of typing an action.”

**Expected result.** The NCR advances through New, Under Investigation, Action Required, Pending Verification, and Closed only when required evidence exists.

**Jira coverage:** QC-12, QC-13, QC-16, and QC-17.

**Important.** CAPA is implemented as governed fields and stages within the NCR. There is not yet a separate qc.capa record with multiple independent action lines.

# 11 Demonstrate reinspection without losing history

1. **From the NCR select Additional Test / Reinspection and click Start Reinspection.**
2. **Show that current result fields are empty.**
3. **Open Inspection History.** Show archived failure, prior review, reason, and old result lines.
4. **Enter new passing values:** Moisture 12, Impurity 1, Hectoliter 77, Wet gluten 25.
5. **Submit and obtain manager approval again.**
6. **Return to the NCR.**
7. **Enter Verification.** Example: “Fresh laboratory sample meets the approved specification and batch identity was confirmed.”
8. **Enter Closure Note and close as Quality Manager.**

> Say: “Reinspection creates a new decision cycle while keeping the first failure immutable in Inspection History. This prevents users from replacing a bad result with a good result and losing evidence.”

**Expected result.** Current inspection is approved, old failed values remain in history, and the NCR closes only after verification.

**Jira coverage:** QC-14, QC-15, and QC-17.

# 12 Demonstrate flour and finished goods checkpoints

## 12.1 Produced flour

1. **Open the prepared flour manufacturing order.**
2. **Show the finished flour lot in Flour Temp Finished.**
3. **Use Quality Lots or open the lot through QC Lots.**
4. **Show automatic Moisture and Wet gluten checks from the Produced Flour plan.**
5. **Attempt release to Flour Store before QC if time permits.** Validation must be blocked.
6. **Enter Moisture 13 and Wet gluten 25, complete, submit, and approve.**
7. **Validate the release to Flour Store.**

> Say: “Flour is finished output of milling but an ingredient for downstream departments. It moves from Flour Temp Finished to Flour Store after QC, rather than to the consumer-product Finished Goods Store.”

**Expected result.** Approved flour reaches Flour Store and becomes available to relevant departments.

**Jira coverage:** QC-06, QC-08, and production release integration.

## 12.2 Pasta bread or biscuit finished product

1. **Open one prepared finished-product manufacturing order.**
2. **Show its lot in the department temporary finished location.**
3. **Open QC lot and show Organoleptic and Packing Weight checks.**
4. **Enter Organoleptic 1 and weight ratio 1.00, then submit and approve.**
5. **Validate transfer to Finished Goods Store.**

> Say: “Production completion places the batch in a temporary finished area. Quality approval is required before it becomes saleable Finished Goods inventory.”

**Expected result.** The approved lot reaches Finished Goods Store and remains linked to its manufacturing order.

**Jira coverage:** QC-07, QC-08, QC-10, and QC-15.

**Important.** The finished-product demo plan uses numeric placeholders for organoleptic and weight ratio. Factory QC must replace them with approved standards.

# 13 Demonstrate reports notifications and audit evidence

## 13.1 QC operational analysis

1. **Open QC Lots.**
2. **Use Data Entry, Awaiting Review, Pending, Passed, On Hold, and Rejected filters.**
3. **Group by Checkpoint, Inspection Status, Product, QC Status, or Plan.**
4. **Switch to Pivot.** Show analysis by checkpoint, product, and disposition.
5. **Switch to Graph.** Show QC lot status by month.

## 13.2 Non-conformance analysis

1. **Open Non-Conformances.**
2. **Filter Overdue or open records.**
3. **Group by product, supplier, severity, owner, state, or disposition.**
4. **Switch to Pivot or Graph.** Show failure quantity or trend.

## 13.3 Printable evidence

1. **Open an approved lot and choose Print > QC Inspection and Release Report.**
2. **Point out plan, statuses, location, reviewer, result lines, users, and timestamps.**
3. **Open an NCR and choose Print > Non-Conformance Report.**
4. **Point out failure, root cause, corrective action, preventive action, verification, and closure.**

> Say: “These reports provide an electronic inspection and non-conformance record. Standard Odoo list export remains available where the user has permission.”

**Jira coverage:** QC-18 and QC-19.

## 13.4 Notifications and audit

- Submission schedules QC review activities for Quality Managers.
- Failure can schedule a failure-review activity.
- NCR owner and due date create or update an investigation activity.
- A daily scheduled job identifies overdue NCRs and notifies managers.
- Chatter tracks governed record changes.
- Result lines record evidence-entry user and time; the lot records submitter, reviewer, decision time, and exception reason.

**Jira coverage:** QC-16 and QC-17.

# 14 Jira coverage and honest implementation status

“Implemented” means there is demonstrable behavior locally. “Partial” means the core outcome exists but proposed sub-scope is not a separate or complete feature. “Discovery” means client confirmation is still required.

| ID | Requirement | Status | Where to show it |
|---|---|---|---|
| QC-01 | Validate QC requirements | Discovery | Use Acceptance Plans and UAT to confirm real tests, limits, sampling, and authorities with factory QC. |
| QC-02 | Design QC architecture and workflows | Implemented | Standalone app, OCA engine, lot workflow, controlled locations, security, and stock gate. |
| QC-03 | Create custom module foundation | Implemented | Quality Control app, menus, models, access, reports, and tests. |
| QC-04 | Inspection plans and parameters | Implemented | Acceptance Plans, versions, effective dates, numeric and qualitative rules. |
| QC-05 | Incoming material inspections | Implemented for governed wheat | Receipt lot enters Wheat Receiving; checks appear; receipt and supplier link. |
| QC-06 | In-process inspections | Partial | Flour release is lot and MO based. Work-order-operation checkpoints are not separately modelled. |
| QC-07 | Finished-goods inspections | Implemented | Produced lots enter temporary finished locations and are blocked before FG release. |
| QC-08 | Laboratory result entry | Implemented | Values, mandatory tests, automatic result, locking, user, and timestamp. |
| QC-09 | Sample tracking | Deferred | No separate physical sample model, reference, retention, or sample status. |
| QC-10 | Inspection approval workflow | Implemented | Data Entry > Awaiting Review > Approved or Rejected, hold, and reinspection. |
| QC-11 | Incoming stock hold and release | Implemented | Wheat Receiving quarantine, blocked validation, release to General Store. |
| QC-12 | Non-conformance management | Implemented | Automatic NCR with source, severity, quantity, owner, state, and disposition. |
| QC-13 | CAPA workflow | Partial but demoable | CAPA fields and controlled closure inside NCR; no separate CAPA object. |
| QC-14 | Reinspection and disposition | Implemented | Snapshot history, reset active fields, linked disposition, new review cycle. |
| QC-15 | Lot traceability | Implemented | Results, receipt, supplier, MO, NCR, history, and stock location linked to lot. |
| QC-16 | QC notifications | Implemented through Odoo activities | Review, failure, owner, and overdue activities. External email or SMS is not configured. |
| QC-17 | QC audit trail | Implemented | Chatter, users, timestamps, result entry, snapshots, and exception reason. |
| QC-18 | Dashboard and operational reports | Implemented through Odoo views | Lists, filters, groups, pivot, graph, overdue and status analysis. |
| QC-19 | Printable and exportable reports | Implemented for core reports | QC and NCR PDFs plus standard export. Separate CAPA and rejection summary templates remain future scope. |

# 15 Questions the client may ask and strong answers

| Question | Answer |
|---|---|
| Why does wheat go to Wheat Receiving? | It is quarantine. The factory has custody, but unrestricted use begins only after controlled release to General Store. |
| Can a warehouse user bypass QC? | Validation blocks pending, held, and rejected lots. Only a Quality Manager can release by exception with a mandatory audited reason. |
| Who decides pass or fail? | The system calculates line results from the plan. The Quality Manager makes the final review decision. |
| Can an inspector change submitted values? | No. Submitted and reviewed results are locked. Correction or reinspection requires a reason and preserves history. |
| What if one mandatory test fails? | The inspection is rejected, the lot is held, and an NCR is created. |
| Can part of a lot pass? | Current decision applies to the lot. Partial acceptance requires confirmed policy and likely controlled lot splitting. |
| Are the demo limits official? | No. They are labelled demo limits; factory Quality must approve real specifications. |
| Why does flour go to Flour Store? | Flour is final mill output but an ingredient downstream. Consumer products go to Finished Goods. |
| Is CAPA included? | CAPA fields, ownership, deadline, verification, and closure are inside NCR. A separate multi-action CAPA record is future scope. |
| Is sample tracking included? | Not yet. Lot inspection is controlled, but physical sample identity and retention require confirmed requirements. |
| Can standards change later? | Yes, through a new effective plan version. Approved plans are locked. |
| Can management analyse supplier failures? | Yes, NCR pivot and graph include supplier, product, severity, quantity, status, and trends when receipt supplier data exists. |
| Does QC work offline? | It is on premises, but users need local network access to the Odoo server. |
| Does it send email? | Odoo activities are created. External email depends on mail-server configuration and agreed policy. |

# 16 Recovery guide during the live demo

| Problem | What to check | Recovery |
|---|---|---|
| Lot absent from QC Lots | Tracking, lot assignment, applicable approved plan. | Open source record and lot directly. Refresh tests only as recovery. |
| Tests missing | Product assignment, effective date, approval. | Fix plan coverage, return to lot, refresh tests. |
| Submit refuses | Mandatory checks remain Pending. | Fill all mandatory results and mark complete. |
| Approval missing | User lacks manager group or record is not submitted. | Use authorised manager and submit first. |
| Result cannot edit | Inspection is submitted or reviewed. | Request correction or reinspection with reason. |
| Transfer blocked after pass | Wrong move lot or QC state. | Confirm lot in Details and verify Passed or Released by Exception. |
| NCR absent | Failure is optional or manager review not completed. | Confirm mandatory failure, submit, and perform manager review. |
| Exception release refuses | Missing reason or manager access. | Enter reason and use Quality Manager. |
| Report unavailable | Wrong record or access. | Print QC report from lot and NCR report from NCR. |
| Unexpected old values | Cache or same record in two tabs. | Refresh and reopen record. |

**Important.** Do not modify code, restart Docker, upgrade modules, or repair database records during the meeting. Switch to a prepared backup record and continue.

# 17 Rehearsal plans

## 17.1 Full 50 minute rehearsal

- 3 minutes: standalone app, architecture, and three checkpoints.
- 5 minutes: governed plan and acceptance rules.
- 8 minutes: incoming wheat pass from receipt to General Store.
- 8 minutes: failure, blocked movement, and NCR.
- 5 minutes: NCR stages and reinspection history.
- 7 minutes: flour and finished-goods release patterns.
- 5 minutes: dashboards, reports, roles, and audit.
- 9 minutes: questions.

## 17.2 Condensed 20 minute route

1. **Open Quality Control and explain three checkpoints.** 2 minutes.
2. **Show one Acceptance Plan and Demo Specification governance.** 3 minutes.
3. **Use a prepared passing wheat lot, submit, approve, and release.** 6 minutes.
4. **Show a failed lot, hold, blocked transfer, NCR, and history.** 5 minutes.
5. **Show flour or finished-product lot, print report, and open pivot.** 4 minutes.

## 17.3 Rehearse these explanations aloud

- Difference between Inspection Status and QC Status.
- Why Wheat Receiving and temporary finished locations exist.
- Why flour goes to Flour Store instead of Finished Goods.
- Why demo limits are not production specifications.
- Why submission and approval are separate.
- How failed mandatory tests create hold and NCR.
- What reinspection preserves.
- What is complete, partial, and deferred in Jira scope.

# 18 Final Saturday checklist

| Check | Done |
|---|:---:|
| Local Odoo opens and ddfsc database is selected | [ ] |
| Administrator or Quality Manager login works | [ ] |
| Quality Control app and menus open | [ ] |
| Incoming Wheat plan and limits are visible | [ ] |
| Passing wheat lot is prepared | [ ] |
| Failing wheat lot is prepared | [ ] |
| Flour lot is prepared in Flour Temp Finished | [ ] |
| Finished-product lot is prepared in Temp Finished | [ ] |
| QC and NCR reports open | [ ] |
| Browser tabs are ordered | [ ] |
| Lot, receipt, and MO references are in presenter notes | [ ] |
| Backup route exists if a live record fails | [ ] |
| Both 20-minute and 50-minute routes were rehearsed | [ ] |

# Closing statement

> Say: “The update converts QC from an informal check into a controlled, traceable release process. It links standards, laboratory evidence, management review, stock quarantine, non-conformance, corrective action, history, and reporting around the same lot. The remaining production-readiness work is to confirm factory specifications, sampling policy, partial-acceptance rules, notification policy, and whether separate physical sample and CAPA records are required.”

End the live demo here and invite the Quality Manager, Production Manager, Warehouse Manager, and Procurement team to confirm remaining policies through UAT.
