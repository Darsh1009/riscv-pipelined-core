# INT8 Systolic-Array Matrix Multiplier

A parameterized N×N **output-stationary systolic array** in SystemVerilog that
computes `C = A × B` for INT8 matrices with INT32 accumulation — the same
dataflow idea at the heart of Google's TPU and most neural-network
accelerators. Verified against a Python reference model with cocotb +
Icarus Verilog, and run through Yosys for hardware-cost estimates.

## Results

All numbers below were measured, not estimated.

| N (array size) | PEs | Latency (cycles) | MACs | MACs/cycle | Generic cells | Flip-flops |
|---|---|---|---|---|---|---|
| 2 | 4  | 5  | 8   | 1.60  | 3,303  | 242   |
| 4 | 16 | 11 | 64  | 5.82  | 13,230 | 978   |
| 8 | 64 | 23 | 512 | 22.26 | 55,999 | 3,986 |

- **Latency is exactly 3N−1 cycles**, matching the analytical derivation (the
  testbench asserts this at every size).
- A single-MAC sequential design needs N³ cycles (64 for N=4), so the array is
  **5.8× faster at N=4 and 22× faster at N=8**.
- Hardware cost grows ≈4× per doubling of N — i.e. O(N²), tracking PE count.
- Cell/flip-flop counts come from **generic Yosys synthesis** (technology-
  independent gates), *not* a real PDK — they show structure and scaling, not
  µm² or timing. See "Next steps" for the OpenLane flow.

## How it works

Each processing element (PE) multiplies the two INT8 values arriving this
cycle, adds the product to a local 32-bit accumulator, and forwards both
inputs onward (A to the right, B downward):

```
          b0     b1     b2     b3        B values flow DOWN
           |      |      |      |
  a0 --> [PE]-->[PE]-->[PE]-->[PE]        A values flow RIGHT
           |      |      |      |
  a1 --> [PE]-->[PE]-->[PE]-->[PE]        Each PE(i,j) accumulates C[i][j]
           |      |      |      |         in place (output-stationary)
  a2 --> [PE]-->[PE]-->[PE]-->[PE]
           |      |      |      |
  a3 --> [PE]-->[PE]-->[PE]-->[PE]
```

**Why skewing matters.** `C[i][j] = Σ_k A[i][k]·B[k][j]`, so PE(i,j) needs
`A[i][k]` and `B[k][j]` to arrive *on the same cycle* for every k. Row i of A
enters i cycles late and column j of B enters j cycles late, so element k of
both reaches PE(i,j) at cycle `i + j + k`. The controller in `matmul_top.sv`
does this skew with a single counter. Zero-padding outside the valid window
means no per-element valid bit is needed (adding 0 changes nothing).

**Latency derivation.** The last product (PE(N−1,N−1), k=N−1) lands at cycle
`3N−3`, so feeding takes `3N−2` cycles, plus one cycle to accept the inputs:
`3N−1` total.

## Files

```
rtl/pe.sv              processing element (multiply-accumulate + pass-through)
rtl/systolic_array.sv  N×N grid of PEs, wired with generate loops
rtl/matmul_top.sv      controller: input capture, skew, start/busy/done handshake
tb/test_matmul.py      cocotb testbench (6 tests, Python reference model)
tb/Makefile            run with `make` or `make N=8`
synth/synth.ys         Yosys script for generic synthesis stats
```

## Run it

```bash
sudo apt-get install iverilog yosys
pip install cocotb

cd tb
make            # N=4 (default)
make N=8        # any N works; N is a parameter, not hard-coded
rm -rf sim_build results.xml   # do this between runs if you change the RTL

cd ../synth
yosys -l synth.log synth.ys     # cell/flip-flop statistics
```

## Verification

`tb/test_matmul.py` checks every result against a pure-Python reference:

| Test | What it catches |
|---|---|
| `test_identity` | wrong skew or index mapping (A×I must equal A) |
| `test_known_small` | hand-checkable diagonal case |
| `test_extremes` | signed-multiply and accumulator-width bugs (−128×−128 etc.) |
| `test_random_many` | 200 random full-range matrix pairs, back to back |
| `test_latency_report` | asserts latency == 3N−1 and prints MACs/cycle |
| `test_busy_ignores_start` | start pulse + changing inputs mid-computation must not corrupt the result |

Passes at N = 2, 3, 4 and 8 (including a non-power-of-two size).

**A measurement bug worth knowing about:** cocotb samples signals just
*before* a clock edge's updates settle, so my first version of the testbench
read `done` one cycle late and reported 12 cycles instead of the true 11. It
was caught because the number didn't match the analytical 3N−1; the fix is to
drive inputs after the rising edge and sample outputs on the falling edge.
Always cross-check a measured number against a derivation.

## Limitations (stated plainly)

- **Utilization is ~35%, not 100%.** Latency is 3N−1 cycles for N³ MACs, so
  MACs/cycle approaches N²/3 for large N, because most PEs sit idle during
  pipeline fill and drain. The design computes one matrix at a time.
- **Verification is simulation-only**: directed + random tests against a
  reference. No formal proof, no coverage metrics, no UVM.
- **Synthesis numbers are generic gates**, not a real process node; no
  timing (critical path / Fmax), area (µm²) or power analysis has been done.
- **The 128-bit A/B input ports are fine for simulation but unrealistic for
  silicon.** A real chip has a limited pin count and needs a narrow load
  interface (serial, or AXI-Stream). This is the first thing to fix before
  any tapeout.
- INT8 only; no saturation or requantization of the INT32 output; matrix
  size fixed at elaboration (no tiling for larger matrices).

## Next steps, roughly in order of payoff

1. **Fix utilization with overlap.** Start loading the next A/B while the
   current result drains (double-buffer the input registers). Steady-state
   throughput approaches N² MACs/cycle. Measure the improvement.
2. **Narrow load/store interface** — an AXI-Stream or simple serial
   interface in place of the flat 128-bit ports.
3. **Run it through OpenLane on Sky130** for real timing slack, area, and
   power, and identify the critical path (likely multiplier → adder).
4. **Quantization stage:** saturate/round INT32 accumulators back to INT8
   so the output can feed the next layer, as real inference hardware does.
5. **Compare dataflows:** build a weight-stationary variant and compare
   latency, utilization, and area against this output-stationary one.
6. **Tiling controller** so a small array can multiply larger matrices.
7. **Tapeout:** a full 4×4 array (~13k generic cells) is far larger than a
   single Tiny Tapeout tile, so it would need a reduced configuration
   (e.g. 2×2, narrower operands, serial load) or multiple tiles. Check the
   current tile size and shuttle dates on tinytapeout.com.
