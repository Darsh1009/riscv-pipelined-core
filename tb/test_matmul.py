import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

N = int(os.environ.get("N", "4"))


# ---------- helpers ----------
def pack_matrix(m, bits=8):
    """Row-major list-of-lists -> one big unsigned integer, element [i][j] at (i*N+j)*bits."""
    v = 0
    for i in range(N):
        for j in range(N):
            v |= (m[i][j] & ((1 << bits) - 1)) << ((i * N + j) * bits)
    return v


def unpack_c(v):
    c = [[0] * N for _ in range(N)]
    for i in range(N):
        for j in range(N):
            raw = (v >> ((i * N + j) * 32)) & 0xFFFFFFFF
            c[i][j] = raw - (1 << 32) if raw & 0x80000000 else raw
    return c


def ref_matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(N)) for j in range(N)] for i in range(N)]


def rand_matrix(lo=-128, hi=127):
    return [[random.randint(lo, hi) for _ in range(N)] for _ in range(N)]


async def reset(dut):
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.a_flat.value = 0
    dut.b_flat.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def run_matmul(dut, a, b, timeout=200):
    """Run one multiplication. Returns (C, cycles from accept edge to done).

    Inputs are driven right after a rising edge; outputs are sampled on the
    falling edge, so we always see settled post-edge values (sampling right
    at RisingEdge would read pre-update values and be off by one cycle).
    """
    dut.a_flat.value = pack_matrix(a)
    dut.b_flat.value = pack_matrix(b)
    dut.start.value = 1
    await RisingEdge(dut.clk)      # accept edge  (cycle 1)
    dut.start.value = 0
    cycles = 1
    while True:
        await FallingEdge(dut.clk)
        if int(dut.done.value) == 1:
            break
        await RisingEdge(dut.clk)
        cycles += 1
        assert cycles < timeout, "timed out waiting for done"
    c = unpack_c(dut.c_flat.value.to_unsigned())
    return c, cycles


def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


# ---------- tests ----------
@cocotb.test()
async def test_identity(dut):
    """A x I = A. Catches wrong skew / index mapping immediately."""
    start_clock(dut)
    await reset(dut)
    a = rand_matrix()
    ident = [[1 if i == j else 0 for j in range(N)] for i in range(N)]
    c, _ = await run_matmul(dut, a, ident)
    assert c == a, f"A x I != A\n got {c}\n exp {a}"


@cocotb.test()
async def test_known_small(dut):
    """Hand-checkable values (only meaningful for N=4)."""
    if N != 4:
        return
    start_clock(dut)
    await reset(dut)
    a = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]]
    b = [[1, 0, 0, 0], [0, 2, 0, 0], [0, 0, 3, 0], [0, 0, 0, 4]]
    c, _ = await run_matmul(dut, a, b)
    exp = [[1, 4, 9, 16], [5, 12, 21, 32], [9, 20, 33, 48], [13, 28, 45, 64]]
    assert c == exp, f"got {c}"


@cocotb.test()
async def test_extremes(dut):
    """Worst-case magnitudes: checks signed multiply and accumulator width."""
    start_clock(dut)
    await reset(dut)
    for va, vb in [(-128, -128), (-128, 127), (127, 127), (127, -128)]:
        a = [[va] * N for _ in range(N)]
        b = [[vb] * N for _ in range(N)]
        c, _ = await run_matmul(dut, a, b)
        assert c == ref_matmul(a, b), f"extreme case {va},{vb}: got {c}"


@cocotb.test()
async def test_random_many(dut):
    """200 random full-range matrix pairs, back to back, vs reference model."""
    start_clock(dut)
    await reset(dut)
    random.seed(1234)
    for t in range(200):
        a, b = rand_matrix(), rand_matrix()
        c, _ = await run_matmul(dut, a, b)
        assert c == ref_matmul(a, b), f"random test {t} mismatch\n A={a}\n B={b}\n got {c}\n exp {ref_matmul(a, b)}"
    dut._log.info("200/200 random matrix multiplications matched the reference")


@cocotb.test()
async def test_latency_report(dut):
    """Measures and reports cycle count; asserts it equals the analytical 3N-1."""
    start_clock(dut)
    await reset(dut)
    a, b = rand_matrix(), rand_matrix()
    c, cycles = await run_matmul(dut, a, b)
    macs = N ** 3
    dut._log.info(f"N={N}: {cycles} cycles for {macs} MACs "
                  f"= {macs / cycles:.2f} MACs/cycle (sequential single-MAC baseline: 1.00)")
    assert cycles == 3 * N - 1, f"latency {cycles} != analytical 3N-1 = {3 * N - 1}"
    assert c == ref_matmul(a, b)


@cocotb.test()
async def test_busy_ignores_start(dut):
    """A start pulse while busy must not corrupt the running computation."""
    start_clock(dut)
    await reset(dut)
    a, b = rand_matrix(), rand_matrix()
    dut.a_flat.value = pack_matrix(a)
    dut.b_flat.value = pack_matrix(b)
    dut.start.value = 1
    await RisingEdge(dut.clk)
    # keep start high and scramble the inputs mid-flight
    dut.a_flat.value = pack_matrix(rand_matrix())
    dut.b_flat.value = pack_matrix(rand_matrix())
    while True:
        await FallingEdge(dut.clk)
        if int(dut.done.value) == 1:
            break
        await RisingEdge(dut.clk)
    c = unpack_c(dut.c_flat.value.to_unsigned())
    dut.start.value = 0
    assert c == ref_matmul(a, b), "start while busy corrupted the result"
