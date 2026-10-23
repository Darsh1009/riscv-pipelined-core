// Matrix-multiply accelerator: C = A x B for N x N INT8 matrices.
//
// Interface: present a_flat/b_flat, pulse `start` for one cycle while idle.
// `busy` is high while computing; `done` pulses for one cycle when c_flat
// holds the result (INT32, row-major).
//
// The controller does the "skewing" that makes a systolic array work:
// row i of A is delayed by i cycles, column j of B by j cycles, so that
// A[i][k] and B[k][j] meet in PE(i,j) on the same cycle.
module matmul_top #(
    parameter N = 4
)(
    input  logic              clk,
    input  logic              rst_n,
    input  logic              start,
    input  logic [N*N*8-1:0]  a_flat,   // A[i][k] = [(i*N+k)*8 +: 8]
    input  logic [N*N*8-1:0]  b_flat,   // B[k][j] = [(k*N+j)*8 +: 8]
    output logic              busy,
    output logic              done,
    output logic [N*N*32-1:0] c_flat    // C[i][j] = [(i*N+j)*32 +: 32]
);
    localparam LAST = 3*N - 3;          // final feed cycle index

    logic [N*N*8-1:0] a_reg, b_reg;
    logic [15:0]      cnt;

    wire accept = start && !busy;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy  <= 1'b0;
            done  <= 1'b0;
            cnt   <= 16'd0;
            a_reg <= '0;
            b_reg <= '0;
        end else begin
            done <= 1'b0;
            if (accept) begin
                a_reg <= a_flat;
                b_reg <= b_flat;
                cnt   <= 16'd0;
                busy  <= 1'b1;
            end else if (busy) begin
                if (cnt == LAST) begin
                    busy <= 1'b0;
                    done <= 1'b1;
                end else begin
                    cnt <= cnt + 16'd1;
                end
            end
        end
    end

    // Skewed operand feed
    logic [N*8-1:0] a_row_flat, b_col_flat;
    integer r, c, k;
    always_comb begin
        a_row_flat = '0;
        b_col_flat = '0;
        for (r = 0; r < N; r = r + 1) begin
            k = cnt - r;
            if (busy && k >= 0 && k < N)
                a_row_flat[r*8 +: 8] = a_reg[(r*N + k)*8 +: 8];
        end
        for (c = 0; c < N; c = c + 1) begin
            k = cnt - c;
            if (busy && k >= 0 && k < N)
                b_col_flat[c*8 +: 8] = b_reg[(k*N + c)*8 +: 8];
        end
    end

    systolic_array #(.N(N)) u_array (
        .clk        (clk),
        .clear      (accept),
        .a_row_flat (a_row_flat),
        .b_col_flat (b_col_flat),
        .c_flat     (c_flat)
    );
endmodule
