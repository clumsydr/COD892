# COD891 / COD892 Presentation — Speaker Guide & Technical Companion

**Presentation Files:**
* Editable slides (12 slides): [`COD891_COD892_Presentation.pptx`](./COD891_COD892_Presentation.pptx)
* PDF preview (12 pages): [`COD891_COD892_Presentation.pdf`](./COD891_COD892_Presentation.pdf)

**Presenter:** Ankit Yadav | **Advisors:** Prof. Rijurekha Sen & Prof. Tarun Mangla | **Institution:** Bharti School of Telecom Technology & Management, IIT Delhi

> **Pacing Strategy (~10–12 minutes total):**
> * **Slides 2–4 (~3 min):** Fast, crisp context on the parser `(a)`, Mahima's dataset `(b)`, and observed 4G/5G throughput `(c)`.
> * **Slides 5–11 (~7.5 min — THE STAR):** Deep dive into the 3GPP log-linear PHY regression `(d)`, pipeline audit (`R²: 0.58 → 0.89 → 0.95`), exact `w ≈ 1` verification, site-by-site predictions, deficit decomposition, and bottleneck shifts.
> * **Slide 12 (~1 min):** Synthesis & future work.

---

## Slide 1 — Title Slide
**What to say (25 seconds):**
> "Good afternoon everyone. Today I will present our work on explaining real-world 4G and 5G application throughput directly from Qualcomm physical-layer baseband logs. I'll briefly cover the custom parser we built, the multi-operator dataset collected by PhD student Mahima, and the observed speeds across 6 locations — and then spend most of the talk on our core result: a 3GPP log-linear PHY regression model that explains **95%** of active application throughput variance and pinpoints exact radio bottlenecks."

---

## Slide 2 — Custom 4G / 5G PHY Log Parser *(Section a — Pre-Regression 1/3)*
**Visual:** Three concise cards (Commercial vs. OSS tools, 4 target logs + hybrid build, NSG analysis vs. licensed Sigma ML) + 4-row sample decoded CSV table.

**What to say (75 seconds):**
> "To access physical-layer metrics like MCS, Resource Blocks, MIMO layers, and HARQ retransmissions, we capture Qualcomm `.qmdl` logs.
> * **4G vs. 5G Tool Gap:** Commercial tools (`QXDM/QCAT`, `Sigma ML`, `NSG`, `TEMS`) decode both 4G and 5G but are costly, GUI-bound, or closed without bulk CSV export. Open-source tools (`MobileInsight`, `SCAT`) work well on mature 4G schemas, but break on modern 5G NR minor versions (`0xB887 v3.6`, `0xB881 v3.1` on our OnePlus 11R).
> * **4 Target Logs & Hybrid Build:** We built standalone pure-Python parsers (`dump_readable_logs.py`) for the minimal sufficient 4-log set — **`0xB887`** (5G DL PDSCH), **`0xB881`** (5G UL TB stats, which replaced `0xB883` after a 3GPP math audit exposed a 78.9% static-shift bug in `0xB883` and confirmed UL is SISO Rank 1), plus **`0xB173`** (4G DL) and **`0xB139`** (4G UL) for 5G NSA anchors and 4G fallback — along with a generalized `nr5g/` engine covering 139 NR codes. We built them using open-source seeds (`mobileinsight.h`, DIAG `0x10 0x00` framing, 8-byte QXDM timestamps), hex alignment & TDD slot checks (`{3,4,5,13,14,15}`), LLMs for bitfield synthesis, and 3GPP TS 38.214 math verification (**94.01%** strict 3-test match across 20,999 grants).
> * **NSG Reverse Engineering vs. Licensed Sigma ML:** To resolve subtle bit-packing ambiguities (padding skips, bitmask gates, `num_layers + 1`), we performed exploratory static analysis of NSG's 55 MB `libqtrun_arch_jni.so` (unlicensed, strictly non-distributable debugging reference). Crucially, we then **legally validated** our standalone parser field-by-field against **Sigma ML**, the commercial parser paid for by Bharti School, achieving exact agreement on identical QMDL captures.
> * **Sample Output:** The bottom table shows real decoded rows — `0xB887` per-slot DL grants (`18,447 B`, `MCS 16`, `133 RBs`, `2 layers`, `RV 0`), `0xB881` cumulative-to-delta UL stats, and 4G `0xB173`/`0xB139` — all harmonized into one common 1-second schema `{MIMO, Q_m, Target Code Rate, RB, Efficiency}`."

---

## Slide 3 — Multi-Operator Field Dataset & Workloads *(Section b — Pre-Regression 2/3)*
**Visual:** Prominent attribution bar (Mahima) + 3 setup blocks + Speedtest vs. DummyVC regime chart (`Fig 1`).

**What to say (50 seconds):**
> "First, an explicit credit: **PhD student Mahima (IIT Delhi) physically collected all of the field data across these 7 locations — not me.** My contribution is the parser pipeline and the regression analysis.
> * **Setup:** Three identical rooted **OnePlus 11R** phones (OxygenOS 14) were orchestrated concurrently over USB ADB (`diag_mdlog` + `tcpdump` + RF logger), testing **Jio (5G SA, 98–100% NR)**, **Airtel (5G NSA, 77–95% NR)**, and **Vodafone (NSA + 100% 4G fallback indoors at `AzadApt`)** across 7 indoor/outdoor sites on 2 days each.
> * **Two Contrasting Workloads (Plot):** **NDT7 Speedtest** (393 runs, bulk TCP to Delhi `del06`) saturates the wireless pipe up to `400+ Mbps` DL (`187 / 98 / 75 Mbps` medians across Jio/Airtel/Vi), whereas **DummyVC** (381 runs, custom bidirectional RTP/UDP video-call emulator) stays tightly **application-capped** at `~5.05 Mbps DL` and `~4.5–4.7 Mbps UL`."

---

## Slide 4 — Throughput Across 6 Sites: UL vs. DL & 4G vs. 5G *(Section c — Pre-Regression 3/3)*
**Visual:** Unified 2×2 figure (`Fig C`): Top row = Speedtest DL vs. UL by operator; Bottom row = active-phase 5G NR (`0xB887`/`0xB881`) vs. 4G LTE (`0xB173`/`0xB139`) PHY throughput across 3 Indoor (`AzadApt`, `Bharti501`, `JiaSarai`) and 3 Outdoor/Mobile (`Ground`, `Car`, `Rajdhani`) sites.

**What to say (55 seconds):**
> "Comparing 3 indoor sites (left of the dashed divider) and 3 outdoor/mobile sites (right) reveals three stark patterns that motivate our regression:
> 1. **5×–30× DL/UL Asymmetry (Top Row):** DL medians hit `140–401 Mbps` while UL sits at `5–51 Mbps` due to DL-heavy TDD slots (~75% DL / 20% UL), 23 dBm UE Tx power limits, and UL SISO.
> 2. **7×–63× 5G DL Gain vs. Narrower UL Gain (Bottom Row):** Directly from uncollapsed QMDL transport blocks, 5G NR DL PHY reaches `71–229 Mbps` vs. `3.6–12.6 Mbps` on 4G LTE — yet in UL, 5G NR narrows to just `1.25×–1.9×` over 4G at `Ground`, `Bharti501`, and `Rajdhani`.
> 3. **Extreme Site Variation:** At indoor `AzadApt`, Jio 5G SA sustains `401 Mbps` DL while Airtel collapses to `5.7 Mbps` and Vodafone falls back to 4G (`3.2 Mbps`). Now let's ask: **can physical-layer regression explain all of this quantitatively?**"

---

## Slide 5 — How Data Is Organized for Regression *(Section d — Star 1/7)*
**Visual:** 4-stage pipeline (`Raw Inputs → 1 s Binning → Align & Filter → Final Matrix`) + 4 real sample rows from `all_data_clean.csv`.

**What to say (55 seconds):**
> "Before looking at regression results, here is exactly how we organize raw baseband logs into the regression matrix where **1 row = 1 second**:
> 1. **Inputs:** For each capture run, we take the 4 decoded QMDL CSVs (`0xB887`, `0xB881`, `0xB173`, `0xB139`) plus the 1-second PCAP throughput CSV.
> 2. **1-Second Binning:** Every transport block inside a 1-second window is aggregated. Because 1 LTE PRB (15 kHz, 1 ms) and 1 NR PRB (30 kHz, 0.5 ms) both equal exactly **168 Resource Elements**, we can sum 4G + 5G RBs directly into total `Resource Blocks (X₃)` and take RB-weighted means for `MIMO (X₁)` and `Spectral Efficiency (X₂)`, plus continuous `Efficiency (X₄)`.
> 3. **Align & Filter:** Per-run cross-correlation fixes the 2–4 s startup clock skew between `tcpdump` and `diag_mdlog`. Then we separate Active Downlink seconds (`DL ≥ UL`) from Active Uplink seconds (`UL > DL`) and trim the first/last ramp-up/teardown second of each phase.
> 4. **Final Matrix:** Look at the 4 real sample rows — as `MIMO`, `SE`, and `RBs` drop from Jio `AzadApt` (`2.89, 3.93, 327,629`) down to Vodafone `AzadApt` (`1.30, 1.50, 18,024`), `Application Throughput` falls right alongside from `411.1 Mbps` down to `3.3 Mbps`."

---

## Slide 6 — 3GPP Log-Linear PHY Elasticity Model *(Section d — Star 2/7)*
**Visual:** Equation centerpiece + `R²` progression table (`0.58 → 0.93 → 0.95` on the exact same `n = 5,163` active rows) + 5 upstream data/modeling fixes.

**What to say (75 seconds):**
> "From 3GPP TS 38.214 physics, physical-layer goodput is multiplicative: $\text{MIMO} \times Q_m \times (R/1024) \times \text{RB} \times \text{Efficiency}$. Taking natural logs converts it into an additive **log-log OLS elasticity regression**:
> $$\ln(\text{Tput}_{\text{App}}) = w_{0,\text{loc,op,dir}} + w_1 \ln(\text{MIMO}) + w_2 \ln(\text{SE}) + w_3 \ln(\text{RB}) + w_4 \ln(\text{Eff}) + \varepsilon_t$$
> Every weight $w_k$ is a dimensionless elasticity: a 1% increase in factor $k$ yields a $w_k\%$ increase in throughput. Under an ideal full pipe, 3GPP physics predicts **$w_k = 1.0$**.
> * **Crucial Pipeline Audit (`R²: 0.58 → 0.93 → 0.95`):** When we first ran regression on the legacy compiled CSVs, $R^2$ was only `0.58` and elasticities were distorted. Auditing the raw pipeline uncovered **5 concrete upstream bugs**:
>   1. `WITHIN_RAT = "max"` threw away 60–80% of multi-slot `0xB887` RBs and dual-codeword `0xB173` MIMO RBs — fixed by summing all slots & simultaneous 4G+5G EN-DC RBs (valid because both 15 kHz LTE and 30 kHz NR PRBs equal exactly 168 REs!).
>   2. `0xB881` used per-TB `avg_prb_this_interval` instead of total `delta_num_prb`.
>   3. 4G DL `0xB173` code rate divided `tb_size_bytes` by bits (`8×` error).
>   4. `0xB881` used binary `_retx == 0` instead of continuous byte-ratio efficiency `new_bytes / (new_bytes + retx_bytes)`.
>   5. Unweighted row means gave 2-RB control slots equal weight to 133-RB data slots, and `tcpdump` vs. `diag_mdlog` had 2–4 s startup skew.
> * Rebuilding cleanly from `qmdl_output` immediately jumped active pooled $R^2$ from `0.58 → 0.93` and stratified active-phase $R^2$ to **`0.95`**!"

---

## Slide 7 — Pooled Active Fit (`n = 5,163`): Combined SE vs. Split MCS *(Section d — Star 3/7)*
**Visual:** 2-panel comparison (`Fig_reg_pooled_vs_split`) on the **exact same `n = 5,163` steady-state active Speedtest rows** used in Slide 8: Panel A = Combined 4-feature SE model (`R² = 0.93`, `SE = +0.95`, `RB = +0.88`, `MIMO = +1.31`, `Eff = +0.54`, `VIF ≤ 1.3`); Panel B = Split 5-feature MCS model (`VIF = 5.2`).

**What to say (60 seconds):**
> "Running both pooled models on the **exact same 5,163 steady-state active Speedtest seconds** ensures an apples-to-apples comparison with our stratified results on the next slide:
> * **Panel A (Combined SE, `R² = 0.93`):** **`Spectral Efficiency = +0.95`** and **`Resource Blocks = +0.88`** sit right in the center of the individual operator slopes we will see next, with clean low VIFs (`1.16–1.33`).
> * **Panel B (Split MCS):** Keeping `Q_m` and `Target Code Rate` separate triggers severe multicollinearity (**`VIF = 4.98 / 5.22`**), pulling `Q_m` up to `+1.12` and pushing `Target Code Rate` down to `+0.73`. Merging them into Spectral Efficiency eliminates collinearity cleanly.
> * **Why Stratify Next?** Notice `MIMO` is inflated to `+1.31` in the pooled active model because pooling Downlink (`MIMO = 1–4`) and Uplink (`SISO = 1`) turns `MIMO > 1` into a partial DL-vs-UL indicator. A formal **Chow F-test** ($F = 75.9, p < 10^{-16}$) confirms we must fit separate `Operator × Direction` models."

---

## Slide 8 — Stratified `Operator × Direction` Fit: $R^2 = 0.95$ (`r = 0.98`) *(Section d — Star 4/7)*
**Visual:** 3-panel regression plot (`Fig 4`: Predicted vs. Actual, Active DL Elasticities, Active UL Elasticities).

**What to say (65 seconds):**
> "Separating each capture into its steady-state Active DL and Active UL phase (`n = 5,163` bins) and fitting 6 independent `Operator × Direction` regressions raises overall fit to **$R^2 = 0.952$, Pearson $r = 0.976$** (and **$R^2 = 0.947$ even without location fixed effects!**):
> * **Panel A (Predicted vs. Actual):** Predictions hug the `y = x` diagonal tightly across four orders of magnitude (`0.1 → 700 Mbps`).
> * **Panel B (Active Downlink):** **Every single elasticity is positive.** Airtel DL (`R² = 0.90`) matches 3GPP across all four factors (`MIMO = +0.90`, `SE = +1.05`, `RB = +0.89`, `Eff = +0.75`). Vodafone DL (`R² = 0.91`) hits `RB = +0.87, SE = +0.82` (with `MIMO = +1.64` reflecting 2×2 MIMO activation co-occurring with high-SINR CA). On Jio DL (`R² = 0.80`), `SE = +0.97` and `MIMO = +0.74`, while `RB = +0.48` because Jio's 100 MHz carrier saturates near its 273-PRB ceiling during peak bursts.
> * **Panel C (Active Uplink — SISO):** Uplink hits **$R^2 = 0.98$ on Jio, $0.97$ on Vodafone, and $0.95$ on Airtel**! With `MIMO = 1` fixed (`w = 0`), **Spectral Efficiency (`+0.91` to `+1.08`)** and **Resource Blocks (`+0.82` to `+1.03`)** sit almost right on `w = 1`. And fixing the binary `0xB881` cliff restored positive `w_Eff` (Jio UL's `-0.63 ± 0.75` is statistically zero because Jio UL has virtually zero retransmissions)."

---

## Slide 9 — Explaining Every Location: Actual vs. PHY-Predicted Speeds *(Section d — Star 5/7)*
**Visual:** 2-panel side-by-side chart (`Fig_reg_by_location`) comparing Actual median active throughput (bars) vs. PHY regression-predicted medians (white diamonds `◆`) across all 18 `(6 Sites × 3 Operators)` pairs in DL and UL.

**What to say (55 seconds):**
> "This slide directly closes the loop with our Slide 4 throughput plots. Each bar is the actual measured median active throughput at that site, and each white diamond is the median predicted purely from our 4 PHY-layer parameters:
> * Across all **18 Site × Operator pairs** in both Downlink (left) and Uplink (right) — spanning `0.5 Mbps` to `416 Mbps` — the diamonds land right on top of the bars.
> * **Why does `AzadApt` show a 150× gap?** Because Jio SA maintains wideband 5G RBs + multi-layer MIMO + high SE indoors (`416` actual vs. `402` predicted), whereas Airtel NSA and Vodafone 4G collapse in RB, SE, and rank (`5.9` and `2.7` Mbps — predicted cleanly to the Mbps).
> * **Why do mobility and UL winners flip across sites** (Airtel leading `Car`, Vodafone leading `Rajdhani` UL at `41 Mbps` vs. Jio `3.3 Mbps`)? Again, 100% tracked by scheduled RBs and achieved Spectral Efficiency."

---

## Slide 10 — Throughput Bottlenecks: Log-Linear Deficit Decomposition *(Section d — Star 6/7)*
**Visual:** 2-panel chart (`Fig 5`: Left = Unified Two-Phase `Bharti501` Airtel Speedtest Timeline; Right = Mean PHY Deficit Share across all 12 `ST/VC × DL/UL × Operator` regimes).

**What to say (65 seconds):**
> "Next, we convert our regression into **Log-Linear Deficit Decomposition** (exact Ceiling-Anchored Linear SHAP): $\Delta_k(t) = w_k \ln(X_k(t) / X_k^{\max})$, measuring how much each parameter pulls second $t$ below the operator's 99th-percentile capacity ceiling:
> * **Panel A (Left — Two-Phase Timeline):** Watch a single `Bharti501` Airtel Speedtest move from Active DL (secs `1–9`, black curve peaking at `210 Mbps` right where the total deficit bar hits its minimum at sec `4`) to Active UL (secs `10–18`, purple curve at `~28 Mbps`). The instant it switches to UL, **Spectral Efficiency / MCS (orange)** explodes as the dominant deficit under the phone's 23 dBm transmit-power ceiling.
> * **Panel B (Right — All 12 Regimes):**
>   * **Speedtest UL (top 3 bars):** Co-dominated by **MCS (`42–58%`)** and **RB (`39–55%`)** — Jio SA UL is **58% MCS-limited**! Retransmissions contribute **≤ 3%**, showing well-tuned commercial OLLA.
>   * **Speedtest DL (middle 3 bars):** Jio SA is evenly balanced (`38%` MCS, `28%` MIMO, `27%` RB) thanks to wide 100 MHz spectrum, whereas Airtel (`49%`) and Vodafone (`48%`) hit RB limits harder.
>   * **DummyVC (bottom 6 bars):** **60–73% RB deficit** across every operator — proving the video call is **application-capped**, not radio-limited."

---

## Slide 11 — Bottleneck Shifts Across Speed Tiers & #1 Constraints *(Section d — Star 7/7)*
**Visual:** 2-panel chart (`Fig_reg_tiers_constraints`): Panel A = Speedtest DL deficit share across 5 throughput tiers (`<10` to `>300 Mbps`); Panel B = Primary (`#1`) constraint classification including App/Transport Residual across all regimes.

**What to say (60 seconds):**
> "Finally, we examine how bottlenecks evolve across speed tiers and how often upper-layer (TCP/app) effects overtake the radio layer:
> * **Panel A (Tier Shift in Speedtest DL):** During poor connections (`<10 Mbps`), **Resource Block starvation (`49%`)** dominates. As speeds rise past `>300 Mbps`, RB share drops to `31%` while **MCS (`31%`)**, **MIMO (`29%`)**, and **Retransmissions (`9%`)** take over as the limiting ceilings.
> * **Panel B (#1 Primary Constraint Classification):** Comparing PHY deficits against the regression residual (`App/Transport Residual`, purple):
>   * During **Speedtest**, the link is **98–99% PHY-limited** — upper-layer residuals are the #1 constraint in only **`0.2%–1.9%`** of active seconds! In Speedtest DL (`>150 Mbps`), RB (`39%`), MCS (`33%`), and MIMO (`26%`) share the #1 spot; in Speedtest UL, it's a pure 50/50 split between MCS (`51%`) and RB (`49%`).
>   * During **DummyVC**, RB under-allocation is #1 in **`76–80%`** of bins (plus **`13%` App/Transport Residual** in VC DL) — cleanly confirming source-limited behavior."

---

## Slide 12 — Key Takeaways & Future Work
**What to say (30 seconds):**
> "To wrap up: we built a Sigma ML-verified 4G/5G PHY parser, showed that clean uncollapsed commercial 4G/5G logs obey 3GPP `w ≈ 1` scaling (`R² = 0.89` pooled, **`R² = 0.95` / `r = 0.98`** stratified), reproduced throughput across all 18 site-operator profiles, and separated radio-limited Speedtest bottlenecks from app-capped video calls. Next steps include 5G SA Carrier Aggregation (`0xB887` Carrier IDs), correlating UE CSI feedback (`0xB881` CQI/RI) against scheduled rank, and non-linear TreeSHAP. Happy to take questions!"

---

## Anticipated Q&A (Defense Prep)

1. **Q: How did fixing the 5 upstream bugs jump $R^2$ from `0.58` to `0.95` (`0.98` on Jio UL)?**
   * **A:** The legacy pipeline silently dropped 60–80% of multi-slot `0xB887` RBs via `WITHIN_RAT="max"`, summed per-TB `avg_prb` instead of total `delta_num_prb` on `0xB881`, divided 4G DL bytes by bits (`8×` error), applied a binary `_retx == 0` cliff to multi-slot 5G UL intervals, and suffered 2–4 s QMDL-vs-PCAP startup skew. Fixing all 5 directly from `qmdl_output` with RB-weighted means and lag alignment snapped all 4 pooled elasticities to `w ≈ 1.0` (`MIMO 1.07, SE 0.96, RB 1.02, Eff 1.16`) and boosted stratified $R^2$ to `0.952` (`0.947` even without location fixed effects).

2. **Q: Why can you sum 4G LTE and 5G NR Resource Blocks together in EN-DC?**
   * **A:** By 3GPP numerology, a 4G LTE PRB at 15 kHz SCS spans `180 kHz × 1 ms = 12 subcarriers × 14 OFDM symbols = 168 REs`. A 5G NR PRB at 30 kHz SCS spans `360 kHz × 0.5 ms = 12 subcarriers × 14 OFDM symbols = 168 REs`. Because both represent the exact same 168-RE time-frequency tile, summing 4G + 5G RBs inside a 1-second bin adds apples to apples.

3. **Q: Why is `Jio DL` RB elasticity `+0.48` while `Airtel/Vodafone DL` are `+0.87–0.89`?**
   * **A:** On Jio's wide 100 MHz 5G SA carrier, saturated Speedtest bursts frequently pin PRB allocation near the 273-PRB ceiling while TCP congestion control / server pacing caps peak rate — compressing within-active RB variance and attenuating `w_RB` slightly compared to NSA/4G where PRB allocations fluctuate more widely.

4. **Q: Why was `0xB883` replaced with `0xB881`, and is the parser legally safe?**
   * **A:** 3GPP TS 38.214 math verification (`verify_mimo_math.py`) caught a **78.9% failure rate** in early `0xB883` parsing (`275 << 5 = 8,800 B` static TB bug & hardcoded Rank 2 vs. live UL SISO). `0xB881` tracks exact cumulative UL counters (`R² = 0.98` on Jio UL). Legally, NSG binary tables are never redistributed; our standalone 4-log Python parser (`dump_readable_logs.py`) is independently verified against Bharti School's **legally licensed Sigma ML** outputs and public 3GPP specs.

5. **Q: Why are the pooled elasticities all `~1.0`, while two stratified elasticities (`Jio DL w_RB = 0.48`, `Vodafone DL w_MIMO = 1.64`) move away from `1.0`?**
   * **A:** Think of it like measuring height vs. weight: across kids to adults (huge range = **Pooled**, `0.05 → 600 Mbps`), small measurement noise barely affects the slope, so all 4 factors land cleanly at `w ≈ 1.0`. Inside one narrow subgroup (only saturated **Jio DL** seconds), Jio pins RBs near the 100 MHz ceiling (`~200K–220K` RBs/s everywhere) while `diag_mdlog` drops some `0xB887` slots under peak load (e.g., `10/16` vs. `16/16` slots/frame). When true RB barely varies and dropped packets add noise, OLS flattens the slope (**attenuation bias**: `w_RB = 0.48`). Conversely, inside **Vodafone DL**, two sites are 100% 4G (`MIMO ≈ 1.1–1.8`, no DIAG drop) while 5G sites have `MIMO ≈ 3.0–3.5` AND ~2× DIAG slot drops, so `MIMO` tracks the 4G→5G switch (`r = 0.80`) and absorbs extra credit (`w_MIMO = 1.64`). Meanwhile, **4 of 6 strata (`Airtel DL`, `Jio UL`, `Airtel UL`, `Vodafone UL`) already sit right around `w ≈ 1.0`**!
