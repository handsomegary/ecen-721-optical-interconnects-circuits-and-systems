// Static tap word decoder and foreground break-before-make controller.
// The control clock periods must satisfy the delays measured for the analog cell.
module lp14_global_control (
    input wire clk,
    input wire reset_n,
    input wire load,
    input wire [9:0] word,
    output reg ready,
    output reg [5:0] tap_a,
    output reg [4:0] tap_b,
    output reg [7:0] tail_a,
    output reg [7:0] tail_b
);
    localparam HOLD = 2'd0, TAILS_OFF = 2'd1, TAPS_OFF = 2'd2, TAPS_ON = 2'd3;
    reg [1:0] state;
    reg [9:0] command;
    wire [2:0] selector_a = word[9:7];
    wire [2:0] selector_b = word[6:4];
    wire [3:0] count_b = word[3:0];
    wire [3:0] tap_a_index = {selector_a, 1'b0};
    wire [3:0] tap_b_index = {selector_b, 1'b1};
    wire adjacent = (tap_a_index + 4'd1 == tap_b_index) ||
                    (tap_b_index + 4'd1 == tap_a_index);
    wire valid = selector_a < 3'd6 && selector_b < 3'd5 &&
                 count_b <= 4'd8 && adjacent;
    integer i;

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            state <= HOLD;
            command <= 10'd0;
            ready <= 1'b1;
            tap_a <= 6'd0;
            tap_b <= 5'd0;
            tail_a <= 8'd0;
            tail_b <= 8'd0;
        end else begin
            case (state)
                HOLD: if (load && valid) begin
                    command <= word;
                    tail_a <= 8'd0;
                    tail_b <= 8'd0;
                    ready <= 1'b0;
                    state <= TAILS_OFF;
                end
                TAILS_OFF: begin
                    tap_a <= 6'd0;
                    tap_b <= 5'd0;
                    state <= TAPS_OFF;
                end
                TAPS_OFF: begin
                    tap_a <= 6'b1 << command[9:7];
                    tap_b <= 5'b1 << command[6:4];
                    state <= TAPS_ON;
                end
                TAPS_ON: begin
                    for (i = 0; i < 8; i = i + 1) begin
                        tail_b[i] <= i < command[3:0];
                        tail_a[i] <= i < (8 - command[3:0]);
                    end
                    ready <= 1'b1;
                    state <= HOLD;
                end
                default: begin
                    tap_a <= 6'd0;
                    tap_b <= 5'd0;
                    tail_a <= 8'd0;
                    tail_b <= 8'd0;
                    ready <= 1'b1;
                    state <= HOLD;
                end
            endcase
        end
    end
endmodule
