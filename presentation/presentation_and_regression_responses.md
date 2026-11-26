# Conversation Record — Presentation Creation & Clean 3GPP PHY Regression Analysis

**Workspace:** `/home/anyada/Documents/cod891`  
**Date:** 2026-11-26  
**Key Generated Deliverables:**
* Final Presentation (12 slides, minimalist, regression-centric): [`COD891_COD892_Presentation.pptx`](./COD891_COD892_Presentation.pptx)
* PDF Preview (12 pages): [`COD891_COD892_Presentation.pdf`](./COD891_COD892_Presentation.pdf)
* Companion Speaker Guide & Q&A: [`COD891_COD892_Speaker_Guide.md`](./COD891_COD892_Speaker_Guide.md)
* Clean Rebuild & Regression Pipeline: [`COD892/scripts/LinearRegression/rebuild_and_regress.py`](./COD892/scripts/LinearRegression/rebuild_and_regress.py) and [`COD892/scripts/LinearRegression/linear_regression.py`](./COD892/scripts/LinearRegression/linear_regression.py)

---

## Turn 1 — Initial Presentation Request (`topresent.txt`)
**User Prompt:**  
> I need to create a presentation based on the guidelines inside `@[topresent.txt]`. Could you make one for me. Thank you.

**Clarifications Confirmed by User:**
1. **Format:** PowerPoint (`.pptx`) + PDF preview.
2. **4G vs. 5G in Section (c):** Use the `COD892` data on disk — show NDT7 UL vs. DL across operators & locations + 4G vs. 5G PHY-layer throughput split from raw QMDL logs (`0xB173`/`0xB139` vs. `0xB887`/`0xB881`).
3. **Framing of NSG vs. Bharti School's Paid Commercial Parser:** Academic & transparent — contrast informal reverse-engineering of NSG (non-commercial / unlicensed) vs. licensed ground-truth verification with Bharti School's paid **Sigma ML**.
4. **Presenter & Course Details:** Ankit Yadav — COD891/COD892, IIT Delhi (later updated to list both advisors: Prof. Rijurekha Sen & Prof. Tarun Mangla).

**Assistant Response Summary:**  
Created an initial 16-slide widescreen presentation covering all parts `(a)–(d)` of `topresent.txt`, backed by real parsed logs (`0xB887`, `0xB881`, `0xB173`, `0xB139`), Mahima's 3-operator dataset (`393` Speedtests, `381` DummyVC runs across 7 locations on 3 identical OnePlus 11R phones), side-by-side UL vs. DL and 4G vs. 5G PHY plots across 6 representative sites (3 Indoor: `AzadApt`, `Bharti501`, `JiaSarai` | 3 Outdoor/Mobile: `Ground`, `Car`, `Rajdhani`), and stratified 3GPP log-linear regression + deficit decomposition plots.

---

## Turn 2 — Fewer Words, Fewer Distractions & Companion Speaker Guide
**User Prompt:**  
> The presentation should have fewer words. Make a second .md document explaining the presentation, and modify the original to have fewer distractions.

**Assistant Response Summary:**  
* Streamlined the PowerPoint deck by cutting on-slide text by **~65%** (short scannable phrases, larger `12–16 pt` body typography, KPI tiles, and 1-line micro-takeaways under plots).
* Removed bordered section pill boxes, redundant subtitles, heavy colored borders, tinted pastel backgrounds, and title-slide stat cards.
* Created [`COD891_COD892_Speaker_Guide.md`](./COD891_COD892_Speaker_Guide.md) containing slide-by-slide spoken talking points, technical explanations, and anticipated defense Q&A.

---

## Turn 3 — Remove Headers & Footers
**User Prompt:**  
> remove the headers and footers as well.

**Assistant Response Summary:**  
Removed all top accent bars, section eyebrow headers, and bottom footers/slide numbers across the entire deck, leaving only the clean slide title and content.

---

## Turn 4 — Two Advisors
**User Prompt:**  
> and their are two advisors, Rijurekha Sen and Tarun Mangla

**Assistant Response Summary:**  
Updated the title slide and [`COD891_COD892_Speaker_Guide.md`](./COD891_COD892_Speaker_Guide.md) to list both advisors: **Prof. Rijurekha Sen & Prof. Tarun Mangla**.

---

## Turn 5 — Remove Presentation Roadmap
**User Prompt:**  
> don't need a presentation roadmap.

**Assistant Response Summary:**  
Removed the Presentation Roadmap slide and renumbered the deck and companion speaker guide cleanly.

---

## Turn 6 — Audit: Should We Redo the Regression Analysis?
**User Prompt:**  
> Do you think we should redo the regression analysis?

**Assistant Response:**  
**Yes — strongly recommended.** Inspecting `COD892/scripts/dataCompilationScripts/build_QMDL_metrics.py` and `COD892/scripts/dataAnalysisScripts/estimate_bw.py` revealed **5 concrete upstream bugs** baked into the legacy `COD892/regression/1000ms/speedtest/all_data.csv` that distorted elasticities (e.g., `Airtel DL w_SE = -0.18` and `Jio DL R² = 0.70`):

1. **Multi-slot & dual-codeword truncation (`WITHIN_RAT = "max"`):** Multiple `0xB887` slots sharing one QXDM packet timestamp (typically 4–6 slots) and dual `0xB173` MIMO codewords were collapsed with `max` instead of `sum`, discarding **60–80% of RBs**.
2. **5G UL used PRBs *per TB* instead of *total PRBs*:** `build_QMDL_metrics.py` mapped 5G UL (`0xB881`) `"Resource blocks"` to `avg_prb_this_interval` instead of `delta_num_prb`, ignoring how many TBs were sent in each interval.
3. **4G DL `Target Code Rate` off by 8×:** `build_QMDL_metrics.py` stored `tb_size_bytes`, while `estimate_bw.py` had `TB_SIZE_IN_BYTES = False`, dividing bytes by bits in `(TBS + 24) / (14 * 12 * RB * Q_m)`.
4. **5G UL `Efficiency` binary cliff:** `estimate_bw.py` checked `_retx == 0`, so any `0xB881` multi-slot interval with $\ge 1$ retransmitted byte marked **100%** of its PRBs as wasted instead of using continuous byte-ratio efficiency `delta_new_tx_bytes / (delta_new_tx_bytes + delta_retx_bytes)`.
5. **Unweighted means & startup clock skew:** `estimate_bw.py` averaged `MIMO`, `Q_m`, and `Target Code Rate` equally across rows (giving a 2-RB control slot equal weight to a 133-RB data slot instead of **RB-weighted means**) and aligned QMDL `t0` to PCAP `sec = 0` without lag alignment.

---

## Turn 7 — Fixing All 5 Bugs & Rerunning the Regression End-to-End
**User Prompt:**  
> Please fix and rerun the regression and all analysis that follows from it. Thank You.

**Assistant Response:**  
Fixed all 5 upstream bugs directly in `build_QMDL_metrics.py` and `estimate_bw.py`, created `COD892/scripts/LinearRegression/rebuild_and_regress.py`, rebuilt the clean 1-second datasets directly from raw uncollapsed `COD892/qmdl_output/` + `COD892/results/Throughput/` (`all_data_clean.csv` for both Speedtest and DummyVC), and reran the stratified regression and active-phase deficit decomposition.

### Before vs. After Fixing the 5 Upstream Bugs

| Metric / Model | Before (Legacy CSV) | After (Clean Rebuild) |
| :--- | :---: | :---: |
| **Pooled 4-Feature Speedtest $R^2$** (`n = 12,707` all rows) | `0.80` (`Eff = -0.54`) | **`0.892`** (`MIMO = +1.07`, `SE = +0.96`, `RB = +1.02`, **`Eff = +1.16`**) |
| **Stratified Active-Phase $R^2$ / $r$** (`n = 5,163` active steady-state) | `0.87` / `0.93` | **`0.952` / `0.976`** (`0.947` even without location fixed effects) |
| **Airtel DL** (`n = 965`) | `R² = 0.77`, `w_SE = -0.18` | **`R² = 0.900`**, `MIMO = +0.90`, **`SE = +1.05`**, `RB = +0.89`, `Eff = +0.75` |
| **Jio UL** (`n = 817`) | `R² = 0.93`, `w_RB = +1.37` | **`R² = 0.984`**, `SE = +0.97`, **`RB = +0.92`** (`MIMO = 0` SISO) |
| **Vodafone UL** (`n = 775`) | `R² = 0.92`, `w_Eff = -0.16` | **`R² = 0.971`**, `SE = +0.91`, **`RB = +1.03`**, `Eff = +0.27` |
| **Airtel UL** (`n = 742`) | `R² = 0.78`, `w_RB = +0.67` | **`R² = 0.951`**, `SE = +1.08`, `RB = +0.82`, `Eff = +0.58` |
| **Vodafone DL** (`n = 1,020`) | `R² = 0.84`, `w_SE = +0.40` | **`R² = 0.912`**, `MIMO = +1.64`, `SE = +0.82`, `RB = +0.87`, `Eff = +1.50` |
| **Jio DL** (`n = 844`) | `R² = 0.70`, `w_Eff = -1.29` | **`R² = 0.800`**, `MIMO = +0.74`, **`SE = +0.97`**, `RB = +0.48`, `Eff = +1.67` |
| **Deficit Decomposition (`Eff / Retx` share)** | Inflated `14–28%` | Realistic **`0.6%–7.0%`** (Speedtest UL: `39–55%` RB + `42–58%` MCS; DummyVC: `60–73%` RB = app-capped) |

*(Chow F-test across `Operator × Direction`: $F = 75.91, p < 10^{-16}$.)*

---

## Turn 8 — Make Regression & Results the Star (Only 2–3 Slides Pre-Regression)
**User Prompt:**  
> I want only 2-3 slides to be spent on the pre-regression part, the regression and its results should be the star of the presentation.

**Assistant Response Summary:**  
Restructured the deck so that **only 3 slides** cover pre-regression setup (`Slide 2: Parser`, `Slide 3: Field Dataset & Mahima Attribution`, `Slide 4: Unified 2×2 Throughput Across 6 Sites`) and **6 dedicated slides** showcase the regression and its results, adding 3 new regression-focused visuals:
* Pooled Combined SE vs. Split MCS comparison (`fig_reg_pooled_vs_split.png`),
* Actual vs. PHY-Predicted median speeds across all 18 `(6 Sites × 3 Operators)` profiles (`fig_reg_by_location.png`),
* Bottleneck shifts across speed tiers (`<10` to `>300 Mbps`) + #1 primary constraint classification (`fig_reg_tiers_constraints.png` — showing Speedtest is **98–99% PHY-limited** with upper-layer residual #1 in only `0.2%–1.9%` of bins, whereas DummyVC is **76–80% RB-underallocated** + `13%` residual in DL).

---

## Turn 9 — Why Do Stratified Elasticities Deviate from `w ≈ 1`?
**User Prompt:**  
> Why are stratified split elasticities so different, shouldn't they be close to 1 as well similar to the pooled elasticities?

**Follow-up User Prompts:**  
> Could you explain this a bit more clearly. I am still lost.  
> First of all add a slide that explain how the data was organised for the regression.

**Assistant Response:**  
1. **Added Slide 5 (`How Data Is Organized for Regression — 1 Row = 1 Second`)** showing the 4-stage pipeline (`Raw Inputs → 1 s Binning → Align & Filter → Final Matrix`) + 4 real rows from `all_data_clean.csv` (`AzadApt Jio DL 411.1 Mbps`, `Bharti501 Airtel DL 152.3 Mbps`, `Bharti501 Airtel UL 22.7 Mbps`, `AzadApt Vodafone DL 3.3 Mbps`), making the final deck **12 slides** (3 pre-regression + 7 regression slides).
2. **Plain-English Explanation of the 3 Stratified Deviations:**
   * First, **4 of 6 strata (`Airtel DL`, `Jio UL`, `Airtel UL`, `Vodafone UL`) already sit near `w ≈ 1.0`** (`0.82–1.08`).
   * **Why `Jio DL w_RB` drops to `0.48` (Attenuation Bias / "Zooming into a Noisy Cluster"):** Jio pins its 100 MHz pipe near full allocation (`~200K–220K RBs/s`) at almost every site, shrinking `std(ln RB)` by **3.3×** (`2.31 → 0.69`). Meanwhile, under 400+ Mbps load, Android's `diag_mdlog` drops some `0xB887` slots (e.g., `AzadApt` Run 1 logged `16/16` DL slots/frame = `616 MB`, while Run 2 logged `10/16` slots/frame = `383 MB`, while App Speedtest stayed at `~400 Mbps`). When logged `RB` jitters horizontally while `App Tput` stays flat, OLS flattens the slope toward zero (`1.0 → 0.48`).
   * **Why `Jio UL w_Eff` is `-0.63 ± 0.75` (Near-Zero Variance):** Active Jio UL has almost zero retransmissions (`Efficiency ≈ 0.98–1.00`, `std(ln Eff) = 0.01`). Fitting a line to points with 1% spread produces a huge standard error (`± 0.75`), statistically indistinguishable from noise.
   * **Why `Vodafone DL w_MIMO` jumps to `+1.64` (4G→5G Hitchhiker):** Two Vodafone sites (`AzadApt`, `Bharti501`) are 100% 4G (`MIMO ≈ 1.1–1.8`, `App/PHY ≈ 1.0`), while 5G sites have `MIMO ≈ 3.0–3.5` AND ~50% `0xB887` DIAG slot drops (`App/PHY ≈ 2.0`). Because `ln(MIMO)` tracks the 4G→5G switch (`r = 0.797`), `MIMO` absorbs that extra 2× jump (`+1.64`).

---

## Turn 10 — How Could Pooled `w_RB > 1` When Individual Strata Were `< 1`? (& Fix)
**User Prompt:**  
> Individually the weight of rbs is less than one, whereas when pooled they become more than one how is that possible?

**Follow-up User Prompt:**  
> Please fix this.

**Assistant Response:**  
Diagnostic verification proved it was **NOT** pooling vs. stratifying — **Slide 7 (Pooled) and Slide 8 (Stratified) had been run on two different sets of rows**:

| Regression Run | Rows Used | `w_RB` |
| :--- | :---: | :---: |
| **1. Pooled ALL** *(incl. low-RB TCP-ACK & ramp-up seconds)* | `12,707` | **`+1.020`** |
| **2. Pooled ALL + 6 `Op×Dir` intercepts** | `12,707` | **`+1.018`** |
| **3. Pooled ACTIVE ONLY** *(same rows as Slide 8, 1 intercept)* | `5,163` | **`+0.879`** |
| **4. Pooled ACTIVE ONLY + 6 `Op×Dir` intercepts** | `5,163` | **`+0.889`** |
| **5. Stratified ACTIVE** *(Slide 8 — 6 strata)* | `5,163` | **`0.48` to `1.03`** *(avg `~0.88`)* |

* **Why `ALL` gave `1.02` vs. `ACTIVE ONLY` gave `0.88`:**
  1. **Header Overhead on Tiny TCP-ACK Seconds:** Low-RB ACK seconds (`~100 RBs`) waste more capacity on MAC/RLC/PDCP/IP headers than full 1500-byte MTU bulk bursts (`~200K RBs`), making the line from bottom-left to top-right slightly steeper (`1.02`).
  2. **Narrower Active Range + `diag_mdlog` Noise:** Restricting to active seconds narrows the RB range from `10,000×` to `30×`, causing mild attenuation to `0.88`.
* **Fix Applied:** Updated Slide 7, `generate_star_figures.py`, `linear_regression.py`, `regression_weights.csv`, `regression_weights_split.csv`, and `COD891_COD892_Speaker_Guide.md` so **both Pooled (Slide 7) and Stratified (Slide 8) run on the exact same `n = 5,163` steady-state active Speedtest rows**:
  * Active Pooled Combined SE (`n = 5,163`, $R^2 = 0.93$): `SE = +0.95`, `RB = +0.88`, `Eff = +0.54`, `MIMO = +1.31`, `VIF ≤ 1.3`.
  * Active Pooled Split MCS (`n = 5,163`, $R^2 = 0.93$): `Q_m = +1.12 (VIF = 4.98)`, `Target Code Rate = +0.73 (VIF = 5.22)`.

---

## Turn 11 — What Is VIF?
**User Prompt:**  
> What is VIF?

**Assistant Response:**  
**VIF (Variance Inflation Factor)** measures how redundant (collinear) one input feature is with the other input features in a regression:
$$\text{VIF}_k = \frac{1}{1 - R_k^2}$$
where $R_k^2$ is how well feature $X_k$ can be predicted from the remaining features.
* $\text{VIF} = 1$: completely independent.
* $\text{VIF} \approx 1\text{–}2$: clean, stable weights.
* $\text{VIF} \ge 5$: high overlap ($R_k^2 \ge 0.80$), causing weights to split unstably.
* In our model, `Q_m` (`VIF = 4.98`) and `Target Code Rate` (`VIF = 5.22`) both come from MCS; merging them into `Spectral Efficiency` drops every feature's VIF to `1.16–1.33`.

---

## Turn 12 — Did We Separate 4G & 5G Buckets, and Do They Follow Different Formulas?
**User Prompt:**  
> In the calculation did you separate the 4G and 5G buckets? Do 4G and 5G follow different calculation formulas?

**Assistant Response:**  
1. **Buckets:** Raw logs (`0xB887`, `0xB881`, `0xB173`, `0xB139`) are decoded separately with their own 4G/5G rules, then **summed together inside each 1-second regression bucket** because 5G NSA (Airtel/Vodafone) uses 4G + 5G simultaneously (EN-DC) while PCAP only measures combined IP throughput. Adding `RB_4G + RB_5G` is physically exact because **1 LTE PRB (15 kHz, 1 ms) = 1 NR PRB (30 kHz, 0.5 ms) = 168 REs**. *(On Slide 4 Panels C/D, 4G and 5G PHY rates are kept strictly separate.)*
2. **Formulas:** Both 4G and 5G obey the exact same OFDM capacity law ($\text{Tput} \propto \text{MIMO} \times Q_m \times R \times \text{RB} \times \text{Efficiency}$). Only field extraction differs:
   * **5G DL (`0xB887`) & 5G UL (`0xB881`):** `(Q_m, R×1024)` from 3GPP TS 38.214 Table 5.1.3.1-2; `0xB881` uses `delta_num_prb` and continuous byte-ratio efficiency.
   * **4G DL (`0xB173`):** `Q_m` from `modulation`, $R \times 1024 = \frac{8 \cdot \text{TB\_bytes} + 24}{156 \cdot \text{RB} \cdot Q_m \cdot \text{layers/TB}} \times 1024$, and `tb_rbs / num_tbs_present` to avoid double-counting dual-codeword 2×2 MIMO.
   * **4G UL (`0xB139`):** `Q_m` from `modulation`, $R \times 1024 = \text{coding\_rate} \times 1024$, `MIMO = 1`, `Efficiency = (is_retx == 0)`.
   * Constant CRS vs. DMRS overhead differences fold cleanly into the log-intercept $w_0$.

---

## Turn 13 — Why Is Pooled Active `Efficiency = 0.54` and `MIMO = 1.31`?
**User Prompt:**  
> Why is the weight got efficiency 0.54 and that for mimo layers 1.31 ? Doesn't that deviate a lot from 1?

**Assistant Response:**  
Yes — both deviate from `1.0` specifically because Slide 7 forced **one single baseline intercept ($w_0$)** across Uplink, Downlink, 4G, and 5G. Keeping ONE shared set of 4 slopes on the **exact same `n = 5,163` active rows** while allowing group intercepts completely eliminates both deviations:

| Pooled Model (`n = 5,163` active rows) | `MIMO` | `SE` | `RB` | `Efficiency` |
| :--- | :---: | :---: | :---: | :---: |
| **1 shared intercept** *(current Slide 7)* | `+1.31` | `+0.95` | `+0.88` | `+0.54` |
| **6 `Operator × Direction` intercepts** | `+1.26` | `+1.01` | `+0.89` | `+0.83` |
| **42 `Location × Operator × Direction` intercepts** (`R² = 0.946`) | **`+1.08`** | **`+0.95`** | **`+0.88`** | **`+0.95`** |

* **Why 1 intercept pushed `MIMO` up (`1.08 → 1.31`):** Uplink always has `MIMO = 1` with a lower baseline `App/PHY` (`0xB881` never drops packets), whereas 5G Downlink has `MIMO = 2–4` with a higher baseline `App/PHY` (lower overhead + some `0xB887` slot drops). With one shared intercept, `MIMO` absorbs that DL baseline jump.
* **Why 1 intercept pulled `Efficiency` down (`0.95 → 0.54`):** 5G Uplink has **higher `Efficiency` (`0.96–0.99`)** and a **lower baseline $w_0$**, while 5G Downlink has **lower `Efficiency` (`0.86–0.91`, ~10% OLLA BLER)** and a **higher baseline $w_0$**. Drawing one single-intercept line through a high-efficiency/lower-y cloud and a low-efficiency/higher-y cloud drags the `Efficiency` slope down from `+0.95` to `+0.54`.
* Allowing `Location × Operator × Direction` fixed-effect intercepts (`w₀`) immediately restores all four elasticities right around `1.0` (`MIMO = +1.08`, `SE = +0.95`, `RB = +0.88`, `Efficiency = +0.95`, $R^2 = 0.946$).
