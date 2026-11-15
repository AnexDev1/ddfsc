# Factory Documents vs DDFSC ERP — Gap Analysis

Date: 2026-11-15 · Compared against `main` @ c6284c6 (ddfsc_manufacturing, ddfsc_quality,
ddfsc_weighbridge, procurement_*, ddfsc_product, ddfsc_sale*).

Source material received from the factory:

* 18 QC forms (OF/QC/001–016, 018A, 019), QC weekly report (QCWR/QCIS/124), QC monthly report May 2026
* Biscuit daily/monthly production workbook (33 sheets, about a year of daily + monthly sheets up to Sept 2026), July monthly
  report, daily consumption report, reconciliation report, FG production report, mill extraction sheet, store list
* 17 photos of paper documents: Store Requisition, Store Issued Voucher, GRN, Wheat Receiving Note,
  Purchase Requisition, FG Receiving Note, FG Store Issue Voucher, Delivery Order, Returned Goods
  Receiving Note, Daily Wheat Flour Transfer Voucher, Bin Card, Weekly Critical Items Report,
  Outgoing (order) Letter, Annual Maintenance Plan, Daily Corrective / Weekly Preventive / Monthly Maintenance reports

Legend: ✅ covered · 🟡 partly covered · ❌ missing. Owner: **A** = Anwar (manufacturing/QC), **M** = Mehbuba (procurement/product/sales).

---

## 1. Headline findings

1. **QC plans are still demo values and too coarse.** The factory has real, signed standards for
   every flour type, wheat type, die and product (tables in §3). We have one plan per checkpoint
   (wheat / flour / finished goods) with placeholder limits, and we are missing test types the
   factory uses daily (ash, protein, hardness, water absorption, cooking test, dry/wet weight).
2. **Half of the QC paperwork is not about a lot at all.** Dryer moisture, magnetic separator,
   instrument calibration, water chlorine/hardness, wheat-in-warehouse monitoring and wheat at
   mixing bins are **shift/day logs**. Our QC model only knows lot inspections.
3. **No printed documents.** The plant runs on numbered, multi-copy, signed vouchers (SIV, GRN,
   FG Receiving Note, Transfer Voucher, Delivery Order…). We have no QWeb print for any of the
   manufacturing/store documents, so the system cannot replace the paper yet.
4. **Material returns and rework are missing.** The biscuit monthly report returns tonnes of
   unused ingredients to store and grinds scrap biscuit back into flour; pasta re-uses "rework
   powder". We only have "by-product to store".
5. **Recipes disagree with real consumption.** Using July 2026 actuals, sugar is −16 %, shortening
   +18 %, citric acid −56 %, film −21 %, tape −22 %, output cartons +8 % vs the BOM. With the 2 %
   tolerance, almost every biscuit MO will demand a variance reason (§6).
6. **The milling model is single-output.** The extraction sheet shows each mill batch produces the
   main flour **plus G2 flour, RF, RC and screenings (impurity)**; our mill BOMs produce one flour + RF.
7. **Store structure does not match the factory.** They have 10 named stores (incl. a remote
   Asama Transit Store at Sabian); we have General Store + Flour Store + one FG Store.

---

## 2. Document-by-document mapping

### 2.1 Quality Control forms

| Form | What it records | Status | Gap |
|---|---|---|---|
| OF/QC/001 Biscuit production follow-up | Per shift: flour gluten, moisture, granulation; per biscuit type dry weight & moisture, packing dry/wet weight with min/max/average | 🟡 | FG plan only has organoleptic + weight ratio. Need per-product plans (Zebib, Defense, New Zebib, Cherry, Fruity), **multi-sample** weights with average, and dry vs wet weight |
| OF/QC/002 Bread baking analysis | Gluten, moisture, granulation, water absorption/qtl; dough weight before baking & baked weight, **sample every 30 min** | 🟡 | Same: need repeated samples per shift + average; limits 114–126 g (120 g) and 95–105 g (100 g); water absorption test type |
| OF/QC/003 Flour transfer report | Per flour type moisture, wet gluten, ash, granulation vs standards | 🟡 | One flour plan for all flours; **no `ash` check type**; standards differ by flour type (§3.2) |
| OF/QC/004 Moisture on dryers | Per shift, per **die number**, per dryer stage (pre-dryer, A1, S1, S2, tiers, Rothoterm, cooler) | 🟡/❌ | `dryer_moisture` type exists but no die, no stage, not a shift log |
| OF/QC/005 Magnetic separator | Per shift: LCP flour / SCP flour / rework powder → present/absent (1700 µm sieve) | ❌ | Shift log, qualitative result |
| OF/QC/006 Moisture tester calibration | Each shift: precision balance, analytical balance, rapid moisture tester | ❌ | Instrument register + calibration log; block result entry with an uncalibrated instrument (optional) |
| OF/QC/007 Organoleptic inspection | Equipment inspected, observation, decision | 🟡 | Free-form inspection; could be an NCR-style record |
| OF/QC/008 Pasta cooking test | Per die: cooking time, water absorption (normal & over-cooking), 5 sensory scores (odor, stickiness, appearance, biting, elasticity), turbidity | ❌ | `cooking` is a single score. Needs a structured test with computed water absorption = (final−initial)/initial |
| OF/QC/009 Pasta packing moisture | Per product, **silo no.**, die-specific max moisture | 🟡 | No die / silo on check |
| OF/QC/010 Pasta packing weight | Per packing machine head (LCP-1 A/B, LCP-2 A/B, SCP), 495–505 g, average | 🟡 | Multi-sample by machine head |
| OF/QC/011 Wheat at transfer | Each morning, per **mixing bin**: wheat type, moisture, HLW, gluten (optional) | ❌ | Shift log keyed by bin |
| OF/QC/012 Records controlling | Register of forms issued by QC to departments | ❌ | Form/document control register |
| OF/QC/013 Chlorine residue & water hardness | Per reservoir chlorine ≤0.5; hardness: pasta mixer old/new 80–150, boiler feed 0–10, bread proofing 80–120 mg/l | ❌ | Utility (Boiler & Utility Division) log |
| OF/QC/014 Wheat milling granulation | Sieve profile >300/>250/>180/>106/<106 µm with ranges; conditioning: lot, bin, initial/final mc, B1, G1, G2, 1st/2nd/total conditioning time | 🟡 | MO already has conditioning hours + initial/final moisture ✅. Missing sieve profile, bin, B1/G1/G2 |
| OF/QC/015 Wheat at receiving | Truck, wheat type (code), HLW, hardness, moisture, impurity, gluten; standards **per wheat type** | 🟡 | One wheat product with demo limits; no wheat type, hardness, protein |
| OF/QC/016 Wheat at warehouse | Per store, wheat type: moisture, HLW, gluten, protein @12.5 % mc, **temperature, RH** | ❌ | Periodic storage monitoring log |
| OF/QC/018A + 019 Product Hold / Release | Product, shape, batch, location, reason, moisture, qty, hold by/approved by, release by/approved by | 🟡 | Lot hold/release exists. Missing: second-signature approval on hold and release, location, quantity, printable form |
| Weekly / Monthly QC report (QCWR/QCIS/124/125) | Averages per section (milling, flour by grade, per die cooler/packing moisture, packing weight, biscuit, bread, water hardness) + table of wheat received | 🟡 | `ddfsc.quality.report` only collects checks by date. Needs computed section averages and the wheat-received table, printable with report number |

### 2.2 Store / inventory documents

| Document | Status | Gap |
|---|---|---|
| Store Requisition (FAOF/PA522) | ✅ `store.requisition` / `ddfsc.store.request` | Print form with Form No., Voucher No., Account No. |
| Store Issued Voucher (SIV, 057351) | 🟡 picking from requisition | Print with unit price, total, balance, **account code**, requisition no., prepared/issued/checked/approved/received; 4-copy distribution note |
| Goods Receiving Note (GRN, 15201) | 🟡 Odoo receipt | Supplier invoice no., PR no., PO no., truck plate, driver on the receipt + print |
| Wheat Receiving Note (PAOF/PA/505) | 🟡 receipt + weighbridge | **Number of bags**, quantity in quintal, **wagon no.** (rail) as well as truck, supplier delivery order no., wheat type/origin (IRS-Russia, IRS-Romania) |
| Purchase Requisition (30451) | 🟡 (M) | "Store information": stock on hand, **min stock, annual consumption** per line |
| Daily Wheat Flour Transfer Voucher (007017) | ✅ component store request | Print form |
| Finished Goods Receiving Note (FDOF/FD/844) | ✅ FG transfer request | FG Transfer Voucher No. reference, print, 5-copy distribution |
| Returned Goods Receiving Note (3504) | 🟡 by-product return only | **Return of unused flour / ingredients from production to store**, with reason |
| FG Store Issue Voucher (PAOF/PA/535) | 🟡 sales delivery (M) | Cash Sales Invoice No., truck plate, print |
| Delivery Order (PAOF/PA/534) | 🟡 (M) | Customer ref no., receiver name + identification, unit cost/total, **gate pass copy** |
| Outgoing Letter (PAOF/PA 571) | 🟡 (M) | Customer order request with "order informed to / approved by / delivered approved by" |
| Bin Card | ❌ | Stock card per product + store: date, GRN/SIV no., received, issued, **running balance** |
| Weekly Report of Critical Items | ❌ | Stock on hand + stock on production floor, monthly consumption, hold limit, ordered qty, received, outstanding, PR no. |
| Store list (10 stores) | 🟡 | See §5 |

### 2.3 Production reports (Biscuit workbook, extraction sheet)

| Report element | Status | Gap |
|---|---|---|
| Per day/line: batches (1 batch = 1.5 qtl flour), cartons, qtl, cartons/qtl | 🟡 | No batch count; cartons/qtl KPI not shown |
| Recycle scrap, sweeping, downtime hours + reason | ✅/🟡 | Downtime reasons too narrow (see §4.6); one downtime per MO |
| FG balance at production (beginning / produced by shift / transferred / ending) | 🟡 | Data exists (temp-finished location) but no report |
| Floor raw-material balance (beginning / received / used / returned / ending) per ingredient & packing | ❌ | Report on department floor location |
| Input/output ratio per ingredient | ✅ | Consumption Variance report covers it |
| Monthly: water used (40 kg/qtl), total dough, disposed dough, product yield, **commercial extraction rate**, **capacity per hour**, working hours | ❌ | Monthly department report |
| Scrap biscuit: produced, % of total, returned, **ground & used as flour** | ❌ | Rework flow |
| Reconciliation: store issues by voucher no. per material vs usage | ❌ | Reconciliation report |
| Mill extraction per batch: bin-scale readings (begin/end ×2), impurity, cleaned wheat, SCP/LCP/G2 flour, RF, RC, extraction % | 🟡 | Multi-output milling, screenings, scale readings (§4.4) |

### 2.4 Maintenance

| Document | Status | Gap |
|---|---|---|
| Annual maintenance plan (PL/MTD/002) – week grid with I (inspection), L (lubrication), S (service) | 🟡 | We create generic weekly + monthly preventive requests. Need PM type I/L/S and the 52-week plan per machine |
| Daily corrective maintenance report (OF/MTD/004) | 🟡 | Request exists; missing shift, start/finish/hours, **downtime hours, spare parts used (issued from store), assigned mechanics, labour cost, manpower** |
| Weekly preventive (OF/MTD/007), Monthly (OF/MD/008) | 🟡 | Reports with work done + maintenance cost |
| Equipment list | 🟡 | Missing biscuit Oven Feeder, 180° Turning Conveyor, Cooling Belt Conveyor; pasta Pre-dryer, Rothoterm, Cooler, packing machines LCP-1/LCP-2/SCP; S.C.P drier |

---

## 3. Real standards to load (replace the DEMO plans)

### 3.1 Wheat at receiving (OF/QC/015)

| Wheat type | HLW kg/hl | Moisture % | Impurity % | Protein % (@11 % mc) | Hard:soft |
|---|---|---|---|---|---|
| Imported hard wheat | ≥ 80 | ≤ 12 | ≤ 6 | ≥ 12 | 80 % |
| Local white hard | ≥ 78 | ≤ 12 | ≤ 8 | – | – |
| Local red mixed | ≥ 75 | ≤ 12 | ≤ 10 | – | – |

Wheat codes used in reports: IRS (imported red soft – Romania/Russia), IHM (imported hard macaroni),
HBL (hard bread local), HML (hard macaroni local), HP / HP1NA / HP2NA (hard pasta), WS (wheat soft).
Gluten is optional at receiving. Current demo plan (moisture ≤13.5, impurity ≤2, HLW ≥76) is **wrong for every type**.

### 3.2 Flour release / transfer (OF/QC/003)

| Flour | Moisture % | Wet gluten % | Ash % | Granulation (through 106 µm) % |
|---|---|---|---|---|
| Spaghetti (LCP) | ≤ 15.5 | ≥ 36 | ≤ 0.55 | 56–63 |
| Macaroni (SCP) | ≤ 15.5 | ≥ 30 | ≤ 0.60 | 56–65 |
| Biscuit | ≤ 15.5 | ≥ 25 | ≤ 0.70 | 58–75 |
| Bread | ≤ 15.5 | ≥ 26 | ≤ 0.65 | 58–73 |

Milling granulation profile for pasta flour (OF/QC/014): >300 µm 2–6, >250 µm 2–5, >180 µm 7–12, >106 µm 18–27, <106 µm 56–63 %.

### 3.3 Finished products

* **Biscuit** (OF/QC/001), dry weight g / moisture %: Zebib 7–8 / ≤8 · Defense 27–28 (31–32) / ≤10 ·
  New Zebib 10.0–10.5 / ≤8 · Cherry 4–5 / ≤3 · Fruity 3.5–4 / ≤3. Packing dry/wet weight limits:
  Zebib 7–8 / 10–11.5, Fruity 3.5–4 / 4.5–5, New Zebib 17–18 / 23–24, Defense 27–28 / 36.5–37.5 (40–43).
* **Bread** (OF/QC/002): 120 g → 114–126 g; 100 g → 95–105 g; weigh 30 min after oven, sample every 30 min.
* **Pasta packing weight** (OF/QC/010): 495–505 g.
* **Pasta packing moisture** (OF/QC/009) by die: LCP 96057 ≤12 (≤11.5 second line); SCP 96025/26 ≤13.7, 108618 ≤13.4, 96036 ≤11, 104297/96038/96032/96041 ≤13.
* **Dryer moisture** (OF/QC/004): ranges per die and stage, e.g. die 115324/25 pre-dryer 25.3–27.7, A1 18.5–20.6, S1 13.2–15.5, S2 12.8–14.3, cooler 12.2–14.0; packing 10–12.5.
* **Cooking test** (OF/QC/008): cooking time 9–12 min (die 96057) / 8–10 (104295), over-cooking 20–24 / 16–20; water absorption ≥140 % / ≥150 % (normal), ≥200 % (over-cooking).

### 3.4 Water (OF/QC/013)

Chlorine residue ≤ 0.5 g/l per reservoir. Hardness: pasta mixer (old/new) 80–150 mg/l, boiler feed 0–10, bread proofing humidifier 80–120.

---

## 4. Recommended changes (manufacturing / QC — owner A)

### 4.1 QC data model

1. **New check types**: `ash`, `protein`, `hardness`, `dry_gluten`, `water_absorption`, `cooking_time`,
   `dry_weight`, `wet_weight`, `temperature`, `humidity`, `water_hardness`, `sensory` (5-point scale).
2. **Product-specific plans**: a plan per flour type / wheat type / finished product (not per
   checkpoint). Load §3 as non-demo starter data (create-only, like `_sync_recipes`).
3. **Wheat type on the lot** (`ddfsc_wheat_type`: IRS, IHM, HBL, HML, HP, WS, local white hard,
   local red mixed + origin country), and plan selection by wheat type.
4. **Multi-sample checks**: a check can hold N samples (time, machine head, value) with computed
   average/min/max; pass rule = average in range and/or every sample in range. Used for bread
   weight, pasta packing weight, biscuit weights.
5. **Context fields on checks**: die number, packing machine/head, silo/bin no., dryer stage.

### 4.2 In-process QC logs (new: `ddfsc.qc.log` + log templates)

One generic "log sheet" model: template (form no., frequency per shift/day, rows to fill, limits),
date, shift, line, rows (subject e.g. "Pre-dryer / die 115324", value or present/absent, limit,
result), recorded by / checked by. Templates from the forms: dryer moisture (004), magnetic
separator (005), instrument calibration (006), wheat at transfer by mixing bin (011), milling
granulation (014), chlorine & water hardness (013), wheat in warehouse with temperature/RH (016).
Add a "missing log" indicator per shift on the Quality dashboard.

### 4.3 Hold / release and QC reports

* Hold and release each need **requester + approver** (two signatures on OF/QC/019/018A), with
  location, quantity, moisture, reason; printable form.
* Weekly/Monthly QC report: compute section averages from checks + logs, include the
  wheat-received table (truck plate, HLW, moisture, hardness, impurity, gluten, germination, use,
  source, unloaded to), number reports `QCWR/QCIS/NNN`, print for the GM.
* Document control register: every form/plan carries Form No., Issue No., prepared by QC,
  reviewed by FSMST, approved by GM, date (already partly in plan versioning); QC-012 issue register.

### 4.4 Milling

* Multi-output mill BOMs: main flour (SCP/LCP/G1) **+ G2 co-product + RF + RC + screenings
  (impurity, loss)**. The extraction sheet shows roughly 82–92 % flour and 20–24 % by-product per batch of wheat.
* Mill batch fields: bin-scale begin/end readings (wheat qtl = difference × 2), impurity removed,
  cleaned wheat; extraction = total flour / wheat.
* **Packed flour SKUs and packing materials**: flour leaves the mill in 10 kg (Vera), 25 kg, 50 kg
  PP bags and by-product in 100 kg bags (bin card "W/F 50 kg biscuit", FG note "W/F 1st 25 kg").
  Add bag-size products/packagings and bag consumption to mill recipes (PP bags + bag closing thread).
* Blending ratios (e.g. pasta = HP1NA % + HP2NA %; macaroni = IRS % + maize flour) as recipe options.

### 4.5 Material flows

* New store request type **`material_return`**: production floor → store, per lot, with reason
  (July biscuit: 20.25 qtl flour, 8 748 kg sugar, 1 797 kg shortening… returned).
* **Rework**: biscuit scrap "ground & used as flour" and pasta rework powder as an allowed
  component (from Recycled Material location `loc_recycle`, which already exists but is unused);
  **disposed dough** as a separate loss figure next to sweepings.
* Paper-voucher reference field on every request/transfer during the transition period (the
  factory will keep pre-printed serial numbers for a while).

### 4.6 Production reporting

* **Batches**: batch size per line (biscuit 1.5 qtl flour) → batches count on the MO.
* **Downtime**: multiple downtime lines per MO (hours + reason + equipment). Add reasons seen in
  the reports: fuel shortage, FG store full, stock count, raw material shortage, transport,
  power cut (exists).
* **Daily department report** (biscuit format): per line & shift — product, batches, cartons, qtl,
  cartons/qtl, scrap, sweeping, downtime; FG floor balance; floor material balance.
* **Monthly department report**: raw materials, chemicals, water (40 kg/qtl), total dough,
  products, scrap %, sweeping, disposed dough, yield, commercial extraction rate, working hours,
  capacity per hour (dough & product), month-end floor inventory, problems faced (free text).
* **Store-issue reconciliation**: per day, voucher no. and quantity received per material vs used.

### 4.7 Product master (biscuit and pasta)

* Biscuit range in the reports and QC forms that is not in the system: New Zebib 78×4 (11 g/pc,
  312 pcs/carton), Zebib, Cherry, Fruity, New biscuit 50×4, Vera Cream (Cappuccino, Apple, Mango),
  Vera Delicious-Chocolate, Vera Cookie-Cinnamon; ingredient whey powder, soya lecithin, vanilla,
  soya bean; films per product (cherry, Lena, white zebib, each cream flavour).
* Orland line runs at 12.5 g/pc vs China line 11 g/pc → product or line-specific conversion.
* Pasta: products by shape, 500 g packs **and 25 kg bags** (weekly report averages 24.4–25 kg),
  die numbers as a master list linked to shape.

### 4.8 Maintenance

* PM type I / L / S on preventive requests and a 52-week plan per machine (annual plan grid).
* Corrective request: shift, start/finish, downtime hours, mechanics, labour cost, manpower,
  **spare parts issued from the Spare Parts store** (linked store issue).
* Daily corrective, weekly preventive, monthly maintenance reports (with cost).
* Complete the equipment list (§2.4).

### 4.9 Printing (all vouchers)

One QWeb layout reproducing the factory header (logo, company name, title, Form No., Issue No.,
Voucher No.), lines table, signature boxes and the copy-distribution footer. Templates, by owner:
**A:** Store Request, Store Issued Voucher, Daily Flour Transfer Voucher, FG Receiving Note,
Returned Goods Receiving Note, Wheat Receiving Note, QC Hold/Release, QC weekly report.
**M:** GRN, Purchase Requisition, FG Store Issue Voucher, Delivery Order (with gate pass copy), Outgoing Letter.

---

## 5. Store structure (factory "Store list")

| Factory store | Today in ERP | Suggestion |
|---|---|---|
| Wheat Store / Silo | Wheat Receiving + 4 wheat silos | ✅ keep; decide silo flow (open item in CLAUDE.md) |
| Packing Materials Store | General Store | Split General Store into child locations |
| Ingredients Store | General Store | 〃 |
| Spare parts & Supplies Store | General Store | 〃 (needed for maintenance spare-part issues) |
| Flour Store | Flour Store | ✅ |
| By-product Store | By-product Temp (per department) | Add a permanent By-product Store as `byproduct_dest` (today returns go to General Store) |
| Pasta & Macaroni Store | Finished Goods Store | Split FG store per family (or child locations) |
| Biscuit Store | 〃 | 〃 |
| Bread Store | 〃 | 〃 |
| Asama Transit Store (Sabian) | – | Separate warehouse (off-site) using `stock.location.transfer` |

Putaway rules can route by product category once the stores are split.

---

## 6. Recipe check against real biscuit data (Zebib, July 2026: 1 515 qtl flour)

| Material (per qtl flour) | BOM | July actual | Diff | Aug actual |
|---|---|---|---|---|
| Sugar kg | 21.60 | 18.05 | −16 % | 15.50 |
| Shortening kg | 5.00 | 5.91 | +18 % | 6.01 |
| Ammonium bicarbonate kg | 3.33 | 3.28 | −1 % | 3.51 |
| Sodium bicarbonate kg | 1.00 | 0.97 | −3 % | 1.00 |
| Sodium metabisulfite kg | 0.08 | 0.08 | 0 % | 0.08 |
| Salt kg | 0.60 | 0.62 | +3 % | 0.60 |
| Citric acid g | 3.30 | 1.45 | −56 % | 1.1 |
| Maize flour share | 10 % | 0.15 % | — | 0 % |
| Output cartons (78×4) | 30 | 32.4 | +8 % | 30.5 |
| Zebib film kg | 4.20 | 3.34 | −21 % | – |
| Scotch tape pcs | 0.43 | 0.34 | −22 % | – |
| Water kg | – | 40 | missing | 40 |

Conclusions:
* The BOM follows the header of the consumption sheet (the official standard). The factory
  doesn't follow it exactly. With a 2 % tolerance, every biscuit MO will need a variance reason.
  Ask the biscuit division which numbers are the standard, or raise the biscuit tolerance.
* Maize flour is effectively not used; the 90/10 split overstates maize demand.
* Defense = 5 cartons/qtl is **confirmed** by the workbook formula (640 pcs × 31.25 g = 20 kg/carton).
* Process water (40 kg/qtl) is missing from the biscuit BOM; it is needed for the total-dough figure.

---

## 7. Data-quality issues the ERP will remove (useful in the demo)

* Extraction sheet batch 9 shows **103 % extraction** (flour > wheat): impossible, a typing error.
* `#DIV/0!` across daily sheets on non-production days; month-end balances typed by hand
  (e.g. "8748 kg Returned").
* Daily consumption report mixes July and August dates in one table.
* 33 sheets with cross-sheet links (`'[1]july daily report,2026'!V227`): one broken link
  breaks the monthly report.

---

## 8. Suggested order of work

| # | Work | Owner | Size |
|---|---|---|---|
| 1 | Load real QC standards (§3) + new check types + wheat type on lots | A | S–M |
| 2 | Material return request type + rework from `loc_recycle` + disposed dough | A | M |
| 3 | Voucher print layout + manufacturing/QC templates (§4.9) | A | M |
| 4 | Multi-sample checks + die/machine/silo context | A | M |
| 5 | QC log sheets (shift logs) + dashboard "missing logs" | A | L |
| 6 | Multi-output milling, packed flour SKUs, bag consumption | A | M |
| 7 | Daily/monthly department reports, floor balance, reconciliation | A | L |
| 8 | Downtime lines + extra reasons; batches | A | S |
| 9 | Store split (10 stores) + putaway by category | A + M | M |
| 10 | Bin card + weekly critical items report | M | M |
| 11 | GRN / Wheat Receiving Note fields (bags, wagon, supplier invoice) + prints | M | S–M |
| 12 | PR store info (min stock, annual consumption); Delivery Order gate pass, receiver ID | M | S |
| 13 | Maintenance: I/L/S plan, spare parts issue, mechanics, labour cost, reports | A | M |
| 14 | Recipe calibration with the biscuit division (§6) | A + factory | S |

Questions for the factory before building:
1. Which biscuit consumption figures are the official standard: the sheet header or the actuals?
2. Is Zebib output standard 30 cartons per qtl of flour or per qtl of product (~29.1)?
3. Should each store (packing, ingredients, spare parts, each FG family) have its own store keeper/approver?
4. Do QC logs need GM approval, or only QC head "checked by"?
5. Are pasta products sold in 25 kg bags as well as 500 g packs (the weekly report averages 24.4–25 kg)?
