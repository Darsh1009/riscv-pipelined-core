// N x N output-stationary systolic array.
// A values enter from the west (one per row), B values from the north
// (one per column). C[i][j] accumulates inside PE(i,j).
// All buses are flattened packed vectors for tool portability.
module systolic_array #(
    parameter N = 4
)(
    input  logic                 clk,
    input  logic                 clear,
    input  logic [N*8-1:0]       a_row_flat,   // west edge, row i = [i*8 +: 8]
    input  logic [N*8-1:0]       b_col_flat,   // north edge, col j = [j*8 +: 8]
    output logic [N*N*32-1:0]    c_flat        // C[i][j] = [(i*N+j)*32 +: 32]
);
    // a_bus: N rows x (N+1) columns of 8-bit wires (extra column = east edge, unused)
    // b_bus: (N+1) rows x N columns of 8-bit wires (extra row = south edge, unused)
    wire [N*(N+1)*8-1:0] a_bus;
    wire [(N+1)*N*8-1:0] b_bus;

    genvar i, j;
    generate
        for (i = 0; i < N; i = i + 1) begin : g_west
            assign a_bus[(i*(N+1))*8 +: 8] = a_row_flat[i*8 +: 8];
        end
        for (j = 0; j < N; j = j + 1) begin : g_north
            assign b_bus[j*8 +: 8] = b_col_flat[j*8 +: 8];
        end

        for (i = 0; i < N; i = i + 1) begin : g_row
            for (j = 0; j < N; j = j + 1) begin : g_col
                pe u_pe (
                    .clk   (clk),
                    .clear (clear),
                    .a_in  (a_bus[(i*(N+1)+j)*8 +: 8]),
                    .b_in  (b_bus[(i*N+j)*8 +: 8]),
                    .a_out (a_bus[(i*(N+1)+j+1)*8 +: 8]),
                    .b_out (b_bus[((i+1)*N+j)*8 +: 8]),
                    .acc   (c_flat[(i*N+j)*32 +: 32])
                );
            end
        end
    endgenerate
endmodule
