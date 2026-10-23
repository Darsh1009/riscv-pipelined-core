// Processing element for an output-stationary systolic array.
// Each cycle: multiply the two incoming INT8 values, add to a local
// 32-bit accumulator, and pass both inputs on (registered) to the
// neighbour to the right (a) and below (b).
module pe (
    input  logic               clk,
    input  logic               clear,   // synchronous: zero acc and pass regs
    input  logic signed [7:0]  a_in,
    input  logic signed [7:0]  b_in,
    output logic signed [7:0]  a_out,
    output logic signed [7:0]  b_out,
    output logic signed [31:0] acc
);
    always_ff @(posedge clk) begin
        if (clear) begin
            a_out <= 8'sd0;
            b_out <= 8'sd0;
            acc   <= 32'sd0;
        end else begin
            a_out <= a_in;
            b_out <= b_in;
            acc   <= acc + a_in * b_in;
        end
    end
endmodule
