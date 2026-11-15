# DDFSC ERP — Manufacturing Demo Guide (Flour → Pasta → Biscuit → Bread)

Study guide for presenting the manufacturing, store and quality system to Dire Dawa Food Complex.
It follows the real paper flow of the factory: **store request → issue → production → shift report →
approval → QC → release → finished-goods store**, department by department, and explains every
option on the way, plus the answers to the questions the factory is likely to ask.

Database: `ddfsc` (http://localhost:8069). Code: `main` @ 208fc65. Last updated 2026-11-15.

---

## Part 0 — Before the demo (do this the day before)

### 0.1 Users to create (Settings ▸ Users & Companies ▸ Users)

The database has only `admin` and `store.manager`. Never demo as admin: admin skips the access
rules real users hit. Create one user per role (password of your choice) and set the
**Department** field on the user form for the department operators.

| Login (suggested) | Role in the factory | Groups to tick | Department |
|---|---|---|---|
| `mill.op` | Flour mill shift supervisor | Manufacturing: User | Flour |
| `pasta.op` | Pasta & macaroni supervisor | Manufacturing: User | Pasta |
| `biscuit.op` | Biscuit supervisor (China + Orland) | Manufacturing: User | Biscuit |
| `bread.op` | Bread supervisor | Manufacturing: User | Bread |
| `opm` | Operation Manager (approves) | Manufacturing: User + **Operation Manager** | *(empty)* |
| `gm` | General Manager | **General Manager** (+ Manufacturing User) | *(empty)* |
| `store.manager` (exists) | Store keeper / store manager | Inventory: Administrator | *(empty)* |
| `qc.assistant` | Assistant quality controller | **DDFSC Quality User** | *(empty)* |
| `qc.head` | QC & Improvement Service head | **DDFSC Quality Manager** | *(empty)* |
| `mechanic` | Maintenance | Maintenance: Equipment Manager + Inventory User | *(empty)* |
| `weighbridge.device` (created) | Scale bridge program only — never log in with it | Weighbridge: Scale Device | *(empty)* |

Rule to remember (they will ask): **a user with a Department sees only that department's lines,
orders, requests and floors. A user without a Department (managers, QC, planning, store) sees all.**

### 0.2 Checklist

1. **QC plans approved** — Quality ▸ DDFSC Standards ▸ Acceptance Plans: the 13 factory plans
   "… (OF/QC/0xx)" are **Approved** (done 2026-11-15). The old "DEMO limits" plans are retired.
2. **Stock to start with** (Inventory ▸ Operations ▸ Receipts, as `store.manager`):
   - Wheat: a receipt from a supplier (see Part 2, step 1) — it lands in **Wheat Receiving**.
   - Ingredients: sugar, shortening, ammonium bicarbonate, sodium bicarbonate, sodium metabisulfite,
     salt, citric acid, maize flour → putaway sends them to **General Store / Ingredients Store**.
   - Packing: Zebib film, Defense film, cartons 78×4 / 160×4, scotch tape, PP bags 10/25/50/100 kg →
     **General Store / Packing Materials Store**.
   - Process water exists as a product (bread recipe); give it a quantity on the Bread Floor or the
     General Store so the bread order can reserve it.
3. **Printer test**: open any transfer ▸ Print ▸ *Plant Voucher* once, so the first print during
   the demo is not slow.
4. **Back-up**: `Claude outputs/backup_and_upgrade.bat` or `pg_dump`. Last backup:
   `Claude outputs/backups/ddfsc-before-gap-closure-20261115-213134.dump`.
5. Open two browsers (or one normal + one private window): operator in one, manager/QC in the other.
   Switching users is the clearest way to show "who can do what".

### 0.3 The map you will keep coming back to

**Departments and lines**

| Department | Lines (work centres) | Floor (where it consumes) | Temp finished (QC hold) | Goes to |
|---|---|---|---|---|
| Flour | MILL – Flour Mill | Mill Floor | Flour Temp Finished | Flour Store |
| Pasta | PASTA – Pasta Line (long cut), MAC – Macaroni Line (short cut) | Pasta Floor / Macaroni Floor | Pasta / Macaroni Temp Finished | Finished Goods Store ▸ Pasta & Macaroni Store |
| Biscuit | BISC-CN – China line, BISC-OR – Orland line | Biscuit Floor | Biscuit Temp Finished | Finished Goods Store ▸ Biscuit Store |
| Bread | BREAD – Bread Line | Bread Floor | Bread Temp Finished | Finished Goods Store ▸ Bread Store |

**Shifts** (Manufacturing ▸ Configuration ▸ Shifts): Shift 1 06–14, Shift 2 14–22, Shift 3 22–06.
Shift 3 after midnight belongs to the **previous production day** (a 02:00 order on the 16th is the
15th's night shift). Times are always factory time (Africa/Addis_Ababa), whatever the user's own
timezone. **Only one order per line per shift per day** is allowed.

**Stores** (Inventory ▸ Configuration ▸ Locations) — matches the Property Administration store list:

| Factory store | In the system |
|---|---|
| Wheat Store / Silo | Wheat Receiving (QC quarantine) → General Store; wheat silos per use (Pasta, Macaroni, Bread, Biscuit) |
| Packing Materials Store | General Store / Packing Materials Store |
| Ingredients Store | General Store / Ingredients Store |
| Spare Parts & Supplies Store | General Store / Spare Parts & Supplies Store |
| Flour Store | Flour Store (+ Pasta / Macaroni Flour Silos) |
| By-product Store | General Store / By-product Store |
| Pasta & Macaroni / Biscuit / Bread Store | Finished Goods Store / … |
| Asama Transit Store (Sabian) | WH / Asama Transit Store (Sabian) |

Why sub-locations: every request still says "General Store" or "Finished Goods Store", and Odoo
takes stock from any of their sub-stores; **putaway rules** decide where received goods land
(sugar → Ingredients Store, film → Packing Materials Store, breakage → By-product Store,
New Zebib → Biscuit Store, …).

**Who approves what**

| Document | Created by | Approved by | Executed by |
|---|---|---|---|
| Store / FG / by-product / material-return request | Department operator | Operation Manager ("Approve and Create Transfer") | Store keeper validates the transfer |
| Production order figures | Department operator ("Submit for Approval") | Operation Manager ("Approve") | Operator "Mark as Done" |
| QC inspection | Assistant QC ("Submit for QC Approval") | QC head ("Approve / Reject Results") | — |
| Release by exception | — | QC Manager only (reason required) | — |
| QC plan | QC Manager | QC Manager ("Approve Plan") | — |
| Wheat silo use | QC pass | General Manager ("GM approve" + intended use) | Store |
| QC log sheet | Assistant QC ("Submit") | QC head ("Checked") | — |

**Paper form ↔ system document** (Print menu on each record)

| Paper form | System | Print |
|---|---|---|
| Store Requisition FAOF/PA522 | Transfer request (MTR/…) | Print ▸ Store Requisition |
| Store Issued Voucher | Transfer from General Store | Print ▸ Plant Voucher |
| Daily Wheat Flour Transfer Voucher | Transfer from Flour Store | Print ▸ Plant Voucher |
| Finished Goods Receiving Note FDOF/FD/844 | FG transfer (FGR/…) | Print ▸ Plant Voucher |
| Finished Products & Other Returned Goods Receiving Note | By-product (BPR/…) or material return (MRN/…) transfer | Print ▸ Plant Voucher |
| Wheat Receiving Note PAOF/PA/505 | Wheat receipt | Print ▸ Plant Voucher |
| Goods Receiving Note | Other receipts | Print ▸ Plant Voucher |
| Delivery Order PAOF/PA/534 (+ gate pass copy) | Delivery | Print ▸ Plant Voucher |
| Product Hold OF/QC/019 / Release OF/QC/018A | Lot | Print ▸ QC Hold / Release Form |
| Bin Card | Stock Card | Inventory ▸ Reporting ▸ Stock Card (Bin Card) |
| Weekly Report of Critical Items | Wizard | Inventory ▸ Reporting ▸ Weekly Critical Items |
| Daily / Monthly production report | Wizard | Manufacturing ▸ Reporting ▸ Department Production Report |
| QC forms OF/QC/004–016 (process) | QC Log Sheets | Quality ▸ DDFSC Operations ▸ QC Log Sheets |
| QC forms OF/QC/001–003, 009, 010, 015 (product) | QC Inspection on the lot | Quality ▸ QC Inspections |
| Daily corrective / weekly / monthly maintenance | Maintenance requests | Maintenance ▸ Reporting ▸ Maintenance Report |

Every printed voucher carries the factory header (title, Form No., Issue No., Voucher No.), the
signature boxes and the copy distribution of the paper pad. A **Paper Voucher No.** field
(transfer ▸ *Plant Document* tab) keeps the pre-printed serial while paper and system run side by side.

---

## Part 1 — Common screens, explained once

### 1.1 Transfer Request (Manufacturing ▸ <Department> ▸ …)

Menu items per department:

| Menu | Request type | From → To |
|---|---|---|
| Store Transfer Requests | *Store Transfer* (ingredients, packing, flour, wheat) | Store → department floor (flour from Flour Store; wheat for the mill from General Store) |
| FG Transfer Requests (Flour: *Flour Store Release Requests*) | *Finished Goods Transfer* | Temp Finished → FG store (Flour: → Flour Store) |
| By-product Transfer to Store | *By-product Return* | department By-products Temp → General Store (lands in By-product Store) |
| Return Materials to Store | *Material Return to Store* | department floor → Flour Store (flour) or General Store (everything else) |
| Available Flour / Available Wheat | stock list | what you may request |
| Temp Finished Products / Saleable By-products | stock list | what is waiting for QC / transfer |

Form fields: Request Type, Production Order (when raised from an order), Destination, Request Date,
Requesting Department (fixed to the user's department), Default Source, Return Reason (returns only),
lines (product, unit, source location, **Available** at the source, quantity, lot).

Status bar: **Draft → Waiting Approval → Requested → Received** (or Cancelled).
- *Submit to Manager*: checks lines, quantities > 0, destination; returns need a reason.
- *Approve and Create Transfer* (Operation Manager only): creates the stock transfer, reserves stock.
- The store keeper validates the transfer (Inventory). When it is done the request becomes **Received**
  automatically.
- *Cancel* (also cancels the open transfer), *Reset to Draft* (from Cancelled).

Rules they will test:
- Only products of that department's recipes can be requested (a biscuit user cannot ask for wheat).
- A material return mixing flour with sugar is refused: flour goes back to Flour Store, other
  materials to General Store — make one return each.
- Numbering: MTR (store request), FGR (finished goods), BPR (by-product), MRN (material return).

### 1.2 Production Order (Manufacturing ▸ <Department> ▸ Manufacturing Orders)

Header fields: Product (only the department's products), Production Line, Recipe (BoM), Quantity,
Shift, Shift Supervisor, Production Day.

Buttons (top bar), in the order you meet them:
1. **Confirm** — freezes the *planned* recipe quantities (the standard for variance).
2. **Request Ingredients** — opens a transfer request pre-filled with the order's components and
   quantities, delivered to *this order's* floor (a Macaroni order goes to the Macaroni Floor).
3. Record production: *Quantity producing*, consumed quantities in the Components tab, lot of the
   finished product (generated automatically if empty).
4. **Submit for Approval** — needs a shift; checks consumption against the recipe (see variance).
   Posts saleable breakage to the department By-products Temp and records losses in the chatter.
5. **Approve / Refuse** (Operation Manager). Refuse needs a note; the operator fixes and resubmits
   (*Reset to Draft* appears after a refusal).
6. **Mark as Done** — only when approved. If any figure changed after approval (a component quantity,
   breakage, sweepings, disposed, quantity produced) the approval is **withdrawn** and listed in the
   chatter; the manager approves again.
7. **Open QC** — the QC inspection of the produced lot.
8. **Send to Finished Goods** (Flour: **Release to Flour Store**) — blocked until the lot passes QC
   (or is released by exception). Shows a button that takes you to the QC lot.
9. **View Finished Goods Transfer**, stat buttons *Transfers* and *QC lots*.

Workflow badge: Draft → Confirmed → Waiting Approval → Approved → Done (Needs Changes after refusal).

**Shift Report tab** — everything the shift supervisor writes on paper:
- *Flour requested per line* (standard request size), **Batches** (biscuit: flour used ÷ 1.5 qtl).
- **Stoppages table**: one line per stop — reason, hours, details. Reasons: Power cut, Fuel shortage,
  Short of film/packing material, Raw material shortage, No space in FG store, Stock count,
  Transport, Mixer, Die, Oven, Packing machine, Other. *Total Downtime* and the main (longest)
  reason are calculated. **Log maintenance** appears when a machine stoppage exists and opens a
  corrective maintenance request on the right machine (the operator does not need maintenance rights).
- **Saleable Breakage** (kg for pasta/biscuit/bread) — posted as a saleable by-product.
- **Sweepings / Waste (kg)** — loss, never deducted from good product.
- **Disposed Dough / Product (kg)** — loss (not on mill orders).
- **Reworked Scrap Used (kg)** — pasta and biscuit only (see rework).
- Mill only: conditioning hours, initial/final moisture, **bin scale start/end**, wheat by bin
  scale, *scale vs recorded wheat* gap, **screenings / impurity (kg)**, extraction, unaccounted loss,
  **packing bags used** (10/25/50/100 kg).
- **Variance Explanation** — required when a material is outside the line tolerance (2 %).

**Consumption variance** (Planned vs Actual tab, and Manufacturing ▸ Reporting ▸ Consumption Variance):
for every material: planned (recipe at confirmation), standard for the quantity actually produced,
actual, variance qty / %, value at cost, Loss/Gain/On standard, *Not in recipe*, *Reworked Scrap*,
*Packing Bags*. Rework and bags are planned extras and never ask for an explanation.

### 1.3 QC inspection (Quality ▸ DDFSC Operations ▸ QC Inspections)

Created automatically for every lot of a product covered by an approved plan (wheat received,
flour produced, finished products). Header: lot, product, plan, checkpoint, wheat type / code
(wheat), **die no., packing machine/head** (finished goods), **silo / bin no.**, source receipt or
order, supplier, stock available and where.

Results table: test, required range, **Samples** required, **Sample Readings** (type
`502, 498, 501, 499`), taken / min / max, Result-Average, Test complete, Pass/Fail.
- Rule *Average within limits*: the average decides.
- Rule *Every sample within limits*: one bad pack fails the test even if the average is fine.
- Too few readings → Pending; cannot submit.
- Qualitative tests: type the observed answer (e.g. *Absent*, *Acceptable*).

Buttons: **Submit for QC Approval** (assistant) → **Approve / Reject Results** (QC head) →
Approved (lot *Passed*) or Rejected (lot *On Hold* + automatic **Non-Conformance**).
*Start Reinspection* (needs a reason; the old inspection is kept as Superseded),
*Release to General Store* (incoming wheat only, store manager).

### 1.4 Lot (Inventory ▸ Products ▸ Lots/Serial Numbers, or from the inspection)

Quality status: Pending, Passed, On Hold, Released by Exception, Rejected. Buttons: *Place on Hold*,
*Release by Exception* (QC Manager, reason required — prints as OF/QC/018A), *Reject Lot*.
Wheat lots: **Wheat Type** (Imported Hard / Local White Hard / Local Red Mixed) and **Wheat Code**
(IRS, HBL, HML, HP, IHM, WS) — the type selects the receiving standard.
**Stock gate**: a held or rejected lot cannot leave its location; flour cannot leave Flour Temp
Finished or a flour silo until it passes; nothing leaves a Temp Finished location before QC.

---

## Part 2 — Flour (mill) end to end

Story: *Russian IRS wheat arrives by truck → weighbridge → QC at receiving → released to the store →
the mill requests it → mills → QC on the flour → flour released to the Flour Store → bran to the
by-product store.*

**Step 1 — Wheat arrives (store.manager)**
1. Weighbridge ▸ Tickets ▸ New: Operation *Incoming Receipt*, supplier, plate, driver, product Wheat,
   purchase order or receipt. The **Scale** field shows *Main Weighbridge (Master-K IDé 500)* and
   whether it is **online**.
   - **From the scale** (the bridge program runs on the weighbridge PC; for the demo run it with
     `--simulate` on your laptop): *Capture First Weight from Scale* while the truck is on the
     bridge (gross 38 760 kg), then *Capture Second Weight from Scale* when it comes back empty
     (tare 15 240 kg) → net 23 520 kg. Each weighing stores its source (From Scale) and the
     indicator's **DSD number**; *Complete Ticket* needs no slip photo.
   - Refusals to show: weight still moving ("not stable yet"), empty platform, or no reading for
     10 s ("start the scale bridge").
   - **Typed** fallback (power cut, bridge down): type the weight, *Record Typed First/Second
     Weight* — marked *Typed* in the ticket and the chatter, and the printed slip photo is required
     before completion. Cancelling needs a reason.
   - Set-up and wiring: `ddfsc_weighbridge/docs/SCALE_INTEGRATION.md`.
2. Inventory ▸ Receipts (from the PO, or new): product Wheat, quantity in **quintals**, lot name
   (e.g. `IRS-RUS-0907`; created automatically if left empty). *Plant Document* tab: supplier
   invoice no., supplier delivery order no., truck/wagon no., driver, paper voucher no.;
   *No. of Bags* on the line. Validate → stock lands in **Wheat Receiving** (putaway).
3. Print ▸ Plant Voucher → **Wheat Receiving Note PAOF/PA/505** with supplier, truck, driver,
   bags, quintals, weighbridge net weight.

**Step 2 — QC at receiving (qc.assistant, then qc.head)**
1. Open the wheat lot, set **Wheat Type = Imported Hard Wheat**, Wheat Code IRS. The inspection
   for OF/QC/015 opens: HLW ≥ 80, moisture ≤ 12, impurity ≤ 6, protein ≥ 12 (at 11 % mc),
   hardness ≥ 80.
   - Show: change the type to *Local Red Mixed* before entering results → the inspection is replaced
     (HLW ≥ 75, impurity ≤ 10, no protein). After results are entered the type is locked —
     "start a reinspection".
2. Enter results → Submit for QC Approval → (qc.head) Approve / Reject Results.
3. Fail scenario: moisture 13 → rejected → lot *On Hold* → Non-Conformance created (Part 6).
4. Pass → (store.manager) **Release to General Store** from the inspection → QC Release transfer
   Wheat Receiving → General Store; validate it. A lot can only be released once.
5. Optional silo path (CLAUDE.md open item: the mill currently takes wheat from General Store):
   GM sets *Intended Use* (pasta/macaroni/bread/biscuit) and approves; only then can the lot enter
   or leave the matching wheat silo.

**Step 3 — Mill requests wheat and bags (mill.op → opm → store.manager)**
1. Flour ▸ Manufacturing Orders ▸ New: product *Short Cut Pasta Flour* (or LCP, Grade 1, Grade 2),
   line Flour Mill, recipe MILL-SCP (1.25 qtl wheat per 1 qtl flour + 0.25 qtl RF bran),
   quantity, Shift. Confirm.
2. Enter bags used on the Shift Report (e.g. 50 kg bags 18, 100 kg by-product bags 3) → they become
   components (*Packing Bags*), issued from the Packing Materials Store.
3. **Request Ingredients** → request pre-filled with wheat + bags → Submit to Manager →
   (opm) Approve and Create Transfer → (store.manager) validate → request *Received*. Print →
   Store Issued Voucher.

**Step 4 — Milling and the shift report (mill.op)**
- Record quantity produced and wheat consumed; conditioning 1st/2nd hours, initial/final moisture;
  bin scale start/end (counter difference × 2 = quintals, as on the extraction sheet) — the
  *scale vs recorded wheat* gap shows mismatches; screenings (impurity) kg; sweepings kg;
  stoppages, **silo loss %**. Read the mass balance: wheat used, flour produced, by-product,
  **unaccounted loss/gain** (wheat − flour − by-product − sweepings − screenings), and the three
  extraction rates of the milling manual (p. 215):
  - **CER** (commercial) = total flour ÷ uncleaned wheat grossed up by the silo loss
    (manual example: 75 ÷ 100.2 = **74.85 %**);
  - **TER** (technical) = total flour ÷ conditioned wheat at B1 = uncleaned wheat − screenings +
    water added in conditioning (water = cleaned wheat × (final − initial moisture) ÷
    (100 − final moisture));
  - **EP** (on products) = flour ÷ (flour + bran / by-products).
  The Department Production Report prints the three rates for the period.
- Submit for Approval → (opm) Approve → Mark as Done.
- Talking point: their extraction sheet showed one batch at **103 %** (typing error) and #DIV/0!
  cells; here the figures come from the stock moves and the gap is visible immediately.

**Step 5 — QC on the flour (OF/QC/003)**
- The flour lot is in **Flour Temp Finished** (QC hold). Inspection for *Short Cut Pasta Flour*:
  moisture ≤ 15.5, wet gluten ≥ 30, granulation 56–65 % through 106 µm, ash ≤ 0.6 (recorded, not
  mandatory — the transfer form does not require it).
- Approve → **Release to Flour Store** on the order → FG request → approve → store validates →
  flour in the Flour Store, available to Pasta/Macaroni ("Available Flour").

**Step 6 — By-products and returns**
- Bran (RF) from the recipe is in By-product Temp → *By-product Transfer to Store* → lands in
  General Store / By-product Store (putaway). Print → Returned Goods Receiving Note.
- Unused wheat or bags → *Return Materials to Store* with a reason → General Store.

**Step 7 — Process QC logs for the mill**: OF/QC/011 wheat at transfer (mixing bins 1–4 moisture
and HLW, every morning), OF/QC/014 milling granulation (sieve profile >300…<106 µm), OF/QC/016
wheat in warehouse (weekly, with temperature and humidity). See Part 6.

---

## Part 3 — Pasta & Macaroni

Lines: **PASTA** (long cut / spaghetti, 500 g) and **MAC** (short cut / macaroni, 500 g). Same
department, separate floors and temp-finished locations. Recipes: 1 qtl LCP/SCP flour → 200 packs
of 500 g (assumes 0 % loss — open item to confirm).

1. (pasta.op) New order: Long Cut Pasta 500 g, line *Pasta Line*, shift. Confirm.
   Try the same line + shift twice → refused (one order per line per shift).
2. Request Ingredients → flour from the **Flour Store** → Print gives the **Daily Wheat Flour
   Transfer Voucher** (because the source is the Flour Store). Flour lots that have not passed QC
   cannot leave the flour store/silos.
3. Produce; Shift Report: breakage (kg, saleable), sweepings, disposed product, **reworked scrap**
   (pasta rework powder) — entering e.g. 15 kg adds *Pasta Breakage* as a component requested from
   the store; stoppages (die, packing machine → Log maintenance).
4. Submit → approve → Mark done. Breakage goes to *Pasta By-products Temp*.
5. QC (OF/QC/009 + 010): weight 495–505 g per pack, **4 samples, every one within limits**
   (fresh install; in `ddfsc` the approved plans have 1 sample — show *Create New Version*, set
   Samples 4 / Every sample, approve, retire old); moisture at packing ≤ 12 (long cut, die 96057)
   / ≤ 13 (short cut). Record **Die No.** (e.g. 115288) and **Packing Machine/Head** (LCP-1 A).
   Type readings `502, 498, 510, 499` → fails on the 510 g pack.
6. Pass → **Send to Finished Goods** → FG Receiving Note FDOF/FD/844 → validated into Finished
   Goods Store / **Pasta & Macaroni Store**.
7. QC log sheets: OF/QC/004 dryer moisture (die 115288: pre-dryer 24.5–27.5, A1 17.4–21, S1
   12–14.9, S2 11.6–14, cooler 12–13.8, packing 10–12.5) every shift; OF/QC/005 magnetic separator
   (LCP flour, SCP flour, rework powder = *Absent*) every shift.

---

## Part 4 — Biscuit (China and Orland lines)

Products: **New Zebib 78×4** (30 cartons per qtl of flour recipe; 312 pcs × 11 g per carton) and
**Defense 160×4** (5 cartons per qtl; 640 pcs × 31.25 g = 20 kg per carton). Recipe per 1 qtl flour
(90 kg G2 + 10 kg maize): sugar 21.6 kg, shortening 5, ABC 3.33, SBC 1, SMS 0.08, salt 0.6, citric
3.3 g, cartons, film 4.2 kg, tape 0.43. Batch = 1.5 qtl flour.

1. (biscuit.op) New order New Zebib, line *Biscuit Line China*, Shift 1, quantity in cartons.
   Confirm → Request Ingredients: flour G2 from the Flour Store, ingredients and packing from the
   General Store (picked from Ingredients / Packing Materials stores). Print shows the **Store
   Issued Voucher** with unit price and total value.
2. Produce. Shift report: **Batches** (flour ÷ 1.5), breakage kg, sweepings, **disposed dough**,
   **reworked scrap** (ground biscuit back into dough — requested from the store, consumed on the
   floor, never asks for a variance reason), stoppages (e.g. 2 h power cut + 1.5 h oven +
   0.5 h *No space in FG store*) → total 4 h, main reason Power cut; *Log maintenance* opens the
   oven request.
3. **Variance**: change sugar actual to 15.5 kg/qtl → submit refused with the list of materials
   outside 2 % → write the explanation → submit. Talking point: July actuals vs recipe — sugar
   −16 %, shortening +18 %, citric −56 %, film −21 % (see Part 9 / item 14).
4. Approve → Done → breakage posted to *Biscuit By-products Temp* → By-product transfer → By-product
   Store; unused sugar/film at month end → **Return Materials to Store** (reason "month-end
   balance") → General Store.
5. QC (OF/QC/001): New Zebib dry weight 10.0–10.5 g/piece (5 samples, average) and moisture ≤ 8 %;
   Defense 27–28 g and ≤ 10 %.
6. Send to Finished Goods → Biscuit Store.
7. Orland line: same flow, line *Biscuit Line Orland*; both lines are in the Biscuit department.

---

## Part 5 — Bread

Products: **Market bread 100 g** (1400 per qtl flour) and **University bread 120 g** (1160 per qtl).
Recipe: 1 qtl Grade 1 flour + 55 kg water (open item: no yeast, salt, sugar, improver yet).

1. Order → Request Ingredients (flour G1 from Flour Store) → produce.
2. Shift report shows *Expected scrap from / to* (10–20 % of flour) as a guide; breakage, sweepings,
   disposed dough, stoppages.
3. QC (OF/QC/002): baked weight 95–105 g (100 g) / 114–126 g (120 g), weighed 30 min after the
   oven, **4 samples, every one within limits** (fresh install).
4. Send to Finished Goods → Bread Store.
5. Water hardness for bread proofing (80–120 mg/l) is on the OF/QC/013 daily log.

---

## Part 6 — Quality Control in depth

**Acceptance plans (QC Manager)** — Quality ▸ DDFSC Standards ▸ Acceptance Plans.
- One plan per product (wheat: per wheat type). Lines: test, rule (at least / at most / between),
  min, max, unit/method, mandatory, numeric or qualitative (accepted answers), samples and rule.
- Governance: Draft → **Approve Plan** → locked. To change a limit: **Create New Version** (1.0 →
  1.1), edit, approve; retire the old one. Two approved plans for the same product/checkpoint
  (and wheat type) are refused. Effective from/until dates. A "Demo Specification" plan cannot be
  approved. Approving or retiring re-links waiting lots automatically.
- The 13 plans: wheat ×3 (OF/QC/015), flour ×4 (OF/QC/003), biscuit ×2 (OF/QC/001),
  bread ×2 (OF/QC/002), pasta ×2 (OF/QC/009/010). Limits in
  `docs/FACTORY_DOCUMENTS_GAP_ANALYSIS.md` §3.

**Inspections** — see 1.3. Locked after submission; corrections only by reinspection, and history
is kept (Inspection History / revisions).

**Hold, release, reject** — on the lot. Print ▸ *QC Hold / Release Form* gives OF/QC/019 (hold)
or OF/QC/018A (release) with product, batch, location, moisture, quantity, reason, signatures.

**Non-Conformance (NCR)** — Quality ▸ DDFSC Operations ▸ Non-Conformances. Created automatically
on a rejected inspection (one per lot, a failed reinspection continues the same NCR).
States: New → Under Investigation → Action Required → Pending Verification → Closed (QC Manager).
Severity minor/major/critical; owner, due date (overdue flagged by a daily job); root cause,
corrective and preventive action, verification, closure note; **disposition**: return to
supplier, rework, scrap, additional test/reinspection, release by exception, other.

**QC Log Sheets** — Quality ▸ DDFSC Operations ▸ QC Log Sheets (today by default).
New → choose the template (OF/QC/004 dryer, 005 magnet, 006 calibration, 011 wheat at transfer,
013 chlorine & hardness, 014 granulation, 016 warehouse), date, shift (required for every-shift
sheets). Rows show OK / Out live. Out of standard → remark required → Submit → QC head *Checked*
(or *Send Back*). One sheet per template, date and shift. Templates are editable by the QC Manager
(Log Sheet Templates), e.g. duplicate the dryer sheet for die 115289/115312.

**Quality Overview (dashboard)** — awaiting review, data entry, blocked lots, approved, open /
overdue / critical NCRs, with lists.

**QC Reports** — Quality ▸ DDFSC Operations ▸ QC Reports: weekly report to the GM (date range,
collected checks, note, submitted). Certificates and NCR / inspection / rejection-summary prints
are in the Print menus.

---

## Part 7 — Stores and inventory

- **Putaway**: receive sugar → it lands in Ingredients Store; film → Packing Materials Store;
  breakage/bran → By-product Store; finished products → their FG store.
- **Stock Card (Bin Card)** — Inventory ▸ Reporting ▸ Stock Card, or Manufacturing ▸ Reporting ▸
  Stock Card (Floors & Stores): date, store/floor, item, voucher/reference, from/to, lot, received,
  issued, **running balance**. Filter a production floor → the floor balance and the
  reconciliation of store issues (vouchers) against consumption (production order references).
  Pivot view per month.
- **Weekly Critical Items** — Inventory ▸ Reporting: stock on hand (store), stock on production
  (floors), total, monthly consumption (last 30 days), months of cover, hold limit (min of the
  replenishment rule), ordered-not-received; rows below the hold limit in red. Leave the items empty
  for every ingredient and packing material in the recipes.
- **Material Return / By-product Transfer** — Part 1.1.
- **Delivery Order** — on a delivery, *Plant Document* tab: customer/cash sales ref., receiver name
  and identification, truck plate, driver → Print gives PAOF/PA/534 with unit cost/total and the
  copy list including **Gate Pass**.
- **Purchase Requisition** (procurement, Mehbuba's module): each line now shows *Stock on Hand*,
  *Min. Stock* and *Annual Consumption* — the "Store Information" block of the pink form.

---

## Part 8 — Maintenance

- Equipment per line (Maintenance ▸ Equipment): biscuit mixer, dough lifter, cart, dough thickness
  roller, die, scrap return, **oven feeder**, oven, **180° turning conveyor**, **cooling belt
  conveyor**, conveyor, packing machine; mill roller mill, sifter, magnetic separator, conditioning
  bin; bread mixer/oven/conveyor; pasta/macaroni extruder, **pre-dryer**, dryer, **Rothoterm**,
  **cooler**, packing scale.
- **Annual plan (PL/MTD/002)**: every machine has recurring preventive requests — weekly
  **I – Inspection**, monthly **L – Lubrication**, quarterly **S – Service** (Plan Type field).
- **Corrective request** (from *Log maintenance* or manual): shift, downtime hours, assigned
  mechanics, manpower, labour cost, maintenance done, **spare parts used** → *Issue Spare Parts from
  Store* creates the issue from the Spare Parts & Supplies Store; spare-parts cost + labour =
  maintenance cost.
- **Maintenance Report (Daily / Weekly / Monthly)** — Maintenance ▸ Reporting: pivot by line and
  month of downtime and cost; list with filters by date for the daily/weekly sheets.

---

## Part 9 — Reports to show at the end

| Report | Where | What it replaces |
|---|---|---|
| Department Production Report | Manufacturing ▸ Reporting | Daily report (one day) and monthly report (a month): materials used, products, losses, rework, batches, output per qtl flour, working hours, capacity per hour, downtime by reason, orders, signatures |
| Shift Report | Manufacturing ▸ Reporting | Shift figures per order |
| Planned vs Actual | Manufacturing ▸ Reporting | Output against plan |
| Consumption Variance | Manufacturing ▸ Reporting | Input/output ratio sheets |
| Stock Card | Inventory / Manufacturing ▸ Reporting | Bin cards, floor balance, reconciliation |
| Weekly Critical Items | Inventory ▸ Reporting | Weekly critical items report |
| Maintenance Report | Maintenance ▸ Reporting | Daily/weekly/monthly maintenance reports |
| QC Log Sheets / QC Reports | Quality | QC forms and weekly QC report |

---

## Part 10 — Questions they will ask (and answers)

**General**
- *Can an operator see other departments?* No — the Department on the user limits lines, orders,
  requests and floors. Managers, QC and stores see all.
- *What if the system and the paper disagree during the transition?* Every transfer has a
  *Paper Voucher No.*; prints carry the system voucher number and the same layout as the pads.
- *Can we work offline / power cuts?* Odoo is a web app on the local server; if the server is up,
  any PC on the network works. Paper pads remain the fallback; enter later with the paper number.
- *Who can change the recipe?* Manufacturing managers (Bills of Materials). Upgrades never overwrite
  recipes, QC plans or line settings the factory edited.

**Stores**
- *Why do I not see "Ingredients Store" on the request?* Requests address the General Store; the
  system takes the stock from its sub-stores and the putaway puts receipts in the right one.
- *Can I issue more than is in stock?* No — the transfer reserves only available stock; the line
  shows *Available* at the source before you submit.
- *How do I give back what is left at month end?* Return Materials to Store, with the reason.
- *Where is the bin card?* Stock Card — filter item and store; the balance column is the bin card.

**Production**
- *Why was my order refused at submit?* Consumption outside the 2 % tolerance — write the
  explanation, or correct the figures. Tolerance is per line (Production Line ▸ Variance Tolerance).
- *I changed a number after approval and now it is "waiting approval" again.* Approval is on the
  figures; any change withdraws it (listed in the chatter).
- *Two orders for one shift?* Not allowed per line; use another shift or adjust the order.
- *Night shift after midnight?* Belongs to the previous day automatically.
- *Where do breakage, sweepings, disposed dough go?* Breakage = saleable stock (By-products Temp →
  By-product Store, sellable). Sweepings and disposed dough = loss figures (kg), not stock.
- *How is rework counted?* As an ingredient issued from the store and consumed; the variance register
  marks it "Reworked Scrap" and does not ask for a reason.
- *Batches?* Flour used ÷ flour per batch of the line (biscuit 1.5 qtl).
- *Extraction?* Flour produced ÷ wheat used; the bin scale gives an independent wheat figure.

**Quality**
- *Can production send goods before QC?* No — Temp Finished locations and flour stores are blocked
  until the lot passes or the QC Manager releases it by exception with a written reason.
- *Can QC change a result after submitting?* No — reinspection with a reason; history is kept.
- *Different limits per die?* Inspections record the die; dryer logs are per die (duplicate the
  template for each die). Product plans currently use the main-die limit (open item).
- *How do we change a standard?* New plan version → approve → retire the old one; old lots keep the
  version they were tested with.
- *What happens on failure?* Lot on hold, NCR created, disposition decided (rework, scrap, return,
  retest, exception).

**Maintenance**
- *Who opens a breakdown request?* The operator from the shift report (Log maintenance) or the
  mechanic in Maintenance. The operator does not need maintenance rights.
- *How is maintenance cost known?* Spare parts issued from the store at cost + labour cost.

---

## Part 11 — Honest limits (say them before they find them)

1. **Recipe calibration (item 14)** — needs the factory: biscuit actuals differ from the sheet
   header (sugar −16 %, shortening +18 %, citric −56 %, film −21 %, cartons +8 %, water 40 kg/qtl
   missing; maize ≈ 0 %). Ask which figures are the standard; then update the recipes (or the line
   tolerance). The Consumption Variance report is the tool to agree on it.
2. **Bread recipe** has only flour and water; **pasta** assumes 0 % loss.
3. **Packed flour SKUs** (W/F 25 kg, 50 kg, 10 kg Vera) are not separate products yet — flour is
   tracked in quintals; bags are recorded as packing material used.
4. **Mill co-products** (G2 alongside SCP/LCP, RC) are not in the starter mill recipes; add them as
   by-product lines on the recipe when the factory confirms the ratios.
5. **Pasta moisture by die** — product plans use the main die; per-die limits are on the dryer logs.
6. **Approved plans in `ddfsc` use 1 sample** — create new versions to require several samples.
7. **Wheat silos** exist with GM approval but the mill takes wheat from the General Store — decide
   whether wheat must pass through the silos.
8. Partner modules marked installed but missing code (inventory_operations, inventory, sales_*,
   withholding tax …) are switched off; restore or uninstall them.

---

## Appendix — 20-minute demo script

1. (2 min) Map: departments, stores, roles (Part 0.3).
2. (4 min) Wheat truck → weighbridge → receipt → wheat type → QC → release (Part 2 steps 1–2).
3. (4 min) Mill order: request wheat + bags, shift report, approve, done, flour QC, release (Part 2).
4. (5 min) Biscuit order: request, rework, stoppages + log maintenance, variance refusal, approve,
   QC with samples, send to FG; print the vouchers (Part 4).
5. (2 min) QC log sheet with one out-of-standard row (Part 6).
6. (3 min) Reports: Department Production Report, Stock Card on the biscuit floor, Weekly Critical
   Items, Maintenance Report (Part 9).
