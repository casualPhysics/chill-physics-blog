---


## The runs, in order

Each plot is one run of the step test: setpoint and measured temperature on top, peltier duty below. Fridge ambient is 21 °C.

<figure><img src="bioreactor-temp-calibration/20260914_095939_temp_steps.png" alt="20260914_095939"><figcaption><code>20260914_095939_temp_steps.csv</code></figcaption></figure>

<figure><img src="bioreactor-temp-calibration/20260914_105305_temp_steps.png" alt="20260914_105305"><figcaption><code>20260914_105305_temp_steps.csv</code></figcaption></figure>

<figure><img src="bioreactor-temp-calibration/20260914_153503_temp_steps.png" alt="20260914_153503"><figcaption><code>20260914_153503_temp_steps.csv</code></figcaption></figure>

<figure><img src="bioreactor-temp-calibration/20260914_155511_temp_steps.png" alt="20260914_155511"><figcaption><code>20260914_155511_temp_steps.csv</code></figcaption></figure>

<figure><img src="bioreactor-temp-calibration/20260914_180224_temp_steps.png" alt="20260914_180224"><figcaption><code>20260914_180224_temp_steps.csv</code></figcaption></figure>

<figure><img src="bioreactor-temp-calibration/20260915_105945_temp_steps.png" alt="20260915_105945"><figcaption><code>20260915_105945_temp_steps.csv</code></figcaption></figure>

<figure><img src="bioreactor-temp-calibration/20260914_all_runs.png" alt="All runs on 14 Sep"><figcaption>All runs from 14 September on one axis.</figcaption></figure>

<figure><img src="bioreactor-temp-calibration/20260915_replication_vs_run8.png" alt="Replication vs run 8"><figcaption>Run 8 (14 Sep) against its replication (15 Sep).</figcaption></figure>

## Findings

*The write-up below is the `FINDINGS.md` kept alongside the data on the Pi, reproduced as-is.*

## Temperature Step Calibration — Findings (2026-09-14)

### Test
Oscillate setpoint 21 → 23 → 25 → 27 → 25 → 23 °C (2 °C steps, 2 min holds,
repeating) using the `bioreactor_v3` reference PID
(`temperature_pid_controller`, kp=12, ki=0.015, kd=0, 5 s period, 70% max duty)
driving the peltier, stirrer at 30%, DS18B20 sensor `28-00000f81ba5b`.

### Data
- `data/20260914_080232_temp_steps.csv` — Run 1: reference PID as-is, ~27 min (3 cycles)
- `data/20260914_083008_temp_steps.csv` — Run 2: PID state reset at each step, ~5.5 min
- `data/20260914_084551_temp_steps.csv` — Run 3: settle-based holds (±0.25 C/60 s, 20 min cap)
- `data/20260914_temp_step_analysis.png` — runs 1–2 plotted (temp, setpoint, signed duty)
- `data/calibration.log` — full PID log of latest run

### Run 3 (settle-based): conclusive thermal-runaway evidence
Context: the reactor sits in a fridge held at 21 C by an Inkbird, so ambient
is actively pinned at 21 C. Step 1 (setpoint 21 C, from 25.6 C, PID at
50–70% cool duty):

| step time | temp |
|---|---|
| 0–2 min | 25.6 → 24.6 C — *genuine cooling while the hot side is still cold* |
| 2–20 min | 24.6 → **30.8 C**, monotonic +0.4 C/min at a constant 70% cool duty |

Initial real cooling followed by runaway once the hot side heat-soaks
(~2–3 min) is the signature of a **peltier with no working hot-side heat
removal** — strongly supporting the fan hypothesis (cause 1) over a stuck
DIR pin (cause 2), since a stuck DIR would have heated from t=0.
The settle-based advance worked as designed: the step correctly timed out at
20 min; the run was then manually stopped to avoid further pointless heating
(vessel left at 31 C, passively cooling in the fridge).

**Do not run cooling-side calibration again until the hot-side fan (likely on
one of relay1–4, GPIO 6/13/19/26) is confirmed running during peltier cool
mode.**

### Heat-only controller (runs 4–6, 2026-09-14 afternoon)
Strategy adopted: peltier heats only; the fridge (Inkbird at 21 C) provides
all cooling. Controller = calibrated feedforward + PID trim + hard-off above
setpoint + predictive coast.

- **Run 4** (`20260914_095939`): ff too high (8 %/C) fought the fridge during
  overshoot recovery — 16+ min recoveries, one timeout. Interrupted.
- **Run 5** (`20260914_105305`, 4.6 h, 5.5 cycles): hard-off fix worked
  (all cooling steps settled in 3–6.6 min) but heating steps overshot
  1.7–2.8 C every time (full duty until too close + ~90 s heater-block lag).
  **Calibration extracted:** steady-state duty 23 C: 7.3%, 25 C: 20.9%,
  27 C: 31.8% → **ff = 6.1*(T−21) − 4.9 %** (negative intercept = stirrer
  heat). Passive cooling tau ≈ 9 min confirmed.
- **v3 controller:** calibrated ff + predictive coast (cut heater when
  temp + rate*90 s crosses setpoint) + approach throttle ff+15% within 1 C.
- **Run 6, hold experiment** (`20260914_153503`): 25 C target from 23.2 C —
  settled in 2.1 min, first crest 25.65 C (overshoot 0.65 C vs 2.5 C in v2).
  10-min hold: mean 25.26 C, sd 0.30, range 24.75–25.75, mean duty 6%.
  Character: ~20% duty bursts every ~2.3 min with coasting between; block
  storage gives a +0.6 C sawtooth crest. Good enough to demonstrate
  targeting; for a tighter hold (±0.1 C) switch to steady balance duty
  (~ff) with small PI trim instead of bursts once settled.

### Run 7: hold sweep 21/23/25/27 C (`20260914_155511`, 59 min, v3)
Settle then hold 10 min at each setpoint, single pass:

| Setpoint | Settle | Hold mean | sd | Range | In ±0.25 band | Mean duty |
|---|---|---|---|---|---|---|
| 21 C | 11.3 min | 20.99 | 0.10 | 20.88–21.19 | 100% | 0.6% |
| 23 C | 3.2 min | 23.07 | 0.11 | 22.88–23.25 | 100% | 3.1% |
| 25 C | 2.4 min | 25.23 | 0.29 | 24.75–25.62 | 52% | 6.0% |
| 27 C | 1.8 min | 27.37 | 0.42 | 26.69–28.06 | 39% | 8.4% |

Targeting works across the range; hold quality degrades with height above
ambient (burst-coast limit cycle grows to ±0.7 C at 27 C, riding high).

**Key recalibration:** the hold-phase mean duties are the TRUE balance duties
(0.6 / 3.1 / 6.0 / 8.4%) — the run-5 estimate (7.3/20.9/31.8%) was inflated
~3x by sampling during bursts. True feedforward:
**ff = 1.33*(T−21) + 0.4 %** (excellent linear fit). The inflated ff is also
why v3 rides high: every burst starts ~15% above true balance.

### Run 8: v4 hold sweep (`20260914_180224`, 49 min) — SOLVED
v4 = true-balance ff + trim phase (within ±0.3 C: continuous duty around
balance with PI trim kp=8 ki=0.05, instead of burst/coast; approach phase
unchanged). Same sweep, 10-min holds:

| Setpoint | v4 mean | v4 sd | v4 range | In-band | Duty | (v3 sd / band%) |
|---|---|---|---|---|---|---|
| 21 C | 20.97 | 0.04 | 20.88–21.06 | 100% | 1.3% | 0.10 / 100% |
| 23 C | 23.02 | 0.07 | 22.94–23.19 | 100% | 2.4% | 0.11 / 100% |
| 25 C | 25.04 | 0.07 | 24.88–25.25 | 100% | 5.0% | 0.29 / 52% |
| 27 C | 27.05 | 0.06 | 27.00–27.19 | 100% | 7.0% | 0.42 / 39% |

±0.07 C (1 sd) at every setpoint, 100% in the ±0.25 band, means within
0.05 C of target, settle times 1–3.8 min. The duty trace is a steady 1–7%
ribbon instead of bursts — block never charges, sawtooth gone. This
controller (heat-only, true-balance ff + trim + predictive-coast approach)
is the recommended configuration for temperature targeting on this rig
until the peltier hot-side fan is fixed.

### Run 9: v4 replication sweep (`20260915_105945`, 2026-09-15) — REPRODUCED
Same v4 sweep, next day, stirrer visually confirmed spinning:

| Setpoint | Sep 14 mean/sd/band% | Sep 15 mean/sd/band% | Duty (14→15) |
|---|---|---|---|
| 21 C | 20.97 / 0.04 / 100% | 21.32 / 0.20 / 49% | 1.3 → 0.0% |
| 23 C | 23.02 / 0.07 / 100% | 23.04 / 0.06 / 100% | 2.4 → 2.2% |
| 25 C | 25.04 / 0.07 / 100% | 25.07 / 0.08 / 100% | 5.0 → 5.0% |
| 27 C | 27.05 / 0.06 / 100% | 27.06 / 0.12 / 88% | 7.0 → 6.7% |

Heated setpoints replicate within 0.03 C mean and near-identical balance
duties — the ff calibration and controller behaviour are stable day-to-day.
The 21 C "miss" is the FRIDGE, not the controller: ambient sat ~21.3–21.6 C
during that window (Inkbird hysteresis / compressor phase), the heater was
correctly hard-off the whole time, and the vessel simply cannot go below
whatever the fridge floor is that hour. Heat-only floor = fridge ambient.

Reproduced balance duties with confirmed stirring also retroactively
validate the Sep 14 data (same physical configuration, genuinely mixed
bulk readings). Comparison figure: `20260915_replication_vs_run8.png`.

### Result summary

| | Heating steps | Cooling steps |
|---|---|---|
| Run 1, cycle 1 | Tracked well: reached 23.4 / 25.2 / 27.2 °C within each 2-min hold (~1 °C/min) | 27→25 fell only with low duty; 25→23 incomplete |
| Run 1, cycles 2–3 | Degraded | Oscillation collapsed to ~24–26.4 °C |
| Run 2 (clean PID each step) | n/a (never got past cooling) | 45–70% cooling duty for 5.5 min → temperature **rose** 25.2 → 27.5 °C |

### Issue 1 (primary, hardware): commanded cooling net-HEATS the vessel
With the peltier driven in the *cool* direction at sustained 45–70% duty, the
vessel warmed at ~+0.4 °C/min — even 5 °C above ambient, where passive losses
also help. Meanwhile *heat* direction works fine (~1 °C/min).

The apparent cooling in run 1 (27 → 24 °C, minutes 8–14) happened while duty
was still ramping through low values — consistent with passive loss to
ambient (~21 °C) plus at best weak active cooling, then heat-soak taking over.

Most likely causes, in order:
1. **Hot-side heatsink fan not running** — the calibration config left
   `relays` disabled; if a relay (GPIO 6/13/19/26) powers the peltier fan,
   the hot side heat-soaks and conducts heat back into the vessel. Classic
   over-driven-peltier signature: cooling works briefly/at low duty, net
   heating at sustained high duty.
2. **DIR signal not switching the H-bridge** (loose wire on GPIO 20) — both
   directions would heat; heating rate differences would come from passive
   losses.
3. Peltier driven past its optimal current in cool mode (I²R > pumping).

#### Suggested diagnostic (5 min)
Fixed 40% duty in each direction for 2 min each, watch temp slope — with the
fan relay ON if one of relay1–4 feeds a fan. This separates (1) from (2).

### Issue 2 (software): PID integral windup across setpoint steps
`temperature_pid_controller` is a pure PID with a deliberately unclamped
integral (`# Update integral term (pure PID - no clamping)`, utils.py). Fine
for its designed use (holding one setpoint), but when the plant can't follow
a step within the hold time, the integral winds up without bound — it reached
**-1370** by run 1 cycle 3 (≈ -20 duty% of authority, saturating the output at
max_duty even against fresh setpoints). Each cycle got worse.

Fixed in this test harness (`temp_step_calibration.py`): PID state
(`_temp_integral`, `_temp_last_error`, `_temp_last_derivative`) is reset at
every setpoint change. For production use in `bioreactor_v3`, consider
anti-windup (integral clamp or back-calculation) in
`temperature_pid_controller`.

### Also noted (code smell, bioreactor_v3)
`src/io.py`: `PeltierDriver.set` docstring says `forward: True=forward/heat,
False=reverse/cool`, but `set_peltier_power` maps `'cool'→forward=True` and
`'heat'→forward=False`. Observed behaviour says the *mapping* is right
(heat commands do heat), so the *docstring* is wrong — worth fixing before it
misleads someone.


## Files

- [temp_step_calibration.py](bioreactor-temp-calibration/temp_step_calibration.py) — the controller and step-test harness (also printed in full below)
- [FINDINGS.md](bioreactor-temp-calibration/FINDINGS.md) — the write-up above, as markdown
- [calibration.log](bioreactor-temp-calibration/calibration.log) — full controller log of the final run
- [Session transcript](bioreactor-temp-calibration/transcript.html) — the full Claude Code conversation that produced this, 14–15 Sep 2026 ([markdown](bioreactor-temp-calibration/transcript.md))
- Raw CSVs (5 s samples: time, setpoint, temperature, error, duty, direction, phase):
    - [20260914_080232_temp_steps.csv](bioreactor-temp-calibration/20260914_080232_temp_steps.csv)
    - [20260914_083008_temp_steps.csv](bioreactor-temp-calibration/20260914_083008_temp_steps.csv)
    - [20260914_084551_temp_steps.csv](bioreactor-temp-calibration/20260914_084551_temp_steps.csv)
    - [20260914_095939_temp_steps.csv](bioreactor-temp-calibration/20260914_095939_temp_steps.csv)
    - [20260914_105305_temp_steps.csv](bioreactor-temp-calibration/20260914_105305_temp_steps.csv)
    - [20260914_153503_temp_steps.csv](bioreactor-temp-calibration/20260914_153503_temp_steps.csv)
    - [20260914_155511_temp_steps.csv](bioreactor-temp-calibration/20260914_155511_temp_steps.csv)
    - [20260914_180224_temp_steps.csv](bioreactor-temp-calibration/20260914_180224_temp_steps.csv)
    - [20260915_105945_temp_steps.csv](bioreactor-temp-calibration/20260915_105945_temp_steps.csv)
