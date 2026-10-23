TOPLEVEL_LANG = verilog
SIM ?= icarus

# Array size. Override with:  make N=8
N ?= 4
export N

VERILOG_SOURCES += $(PWD)/../rtl/pe.sv
VERILOG_SOURCES += $(PWD)/../rtl/systolic_array.sv
VERILOG_SOURCES += $(PWD)/../rtl/matmul_top.sv

TOPLEVEL = matmul_top
COCOTB_TEST_MODULES = test_matmul

COMPILE_ARGS += -g2012
COMPILE_ARGS += -Pmatmul_top.N=$(N)

include $(shell cocotb-config --makefiles)/Makefile.sim
