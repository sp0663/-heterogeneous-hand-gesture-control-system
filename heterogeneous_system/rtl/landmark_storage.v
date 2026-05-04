// Stores incoming landmark coordinates into register arrays indexed by landmark_id and asserts frame_ready when the last landmark of the frame is received.

module landmark_storage (
    input clk,
    input rst,

    input valid_in,              // new landmark available
    input [4:0] landmark_id,     // 0–20
    input [15:0] x_in,
    input [15:0] y_in,

    output reg frame_ready,      // high when all landmarks for a frame received

    output reg [335:0] x_out,
    output reg [335:0] y_out
);
    reg [4:0] count;
    
    always @(posedge clk) begin
        if (rst) begin
            frame_ready <= 0;
            x_out <= 0;
            y_out <= 0;
            count <= 0;
        end
        else begin
            frame_ready <= 0;
            if (valid_in && count < 21) begin
                x_out[landmark_id * 16 +: 16] <= x_in;
                y_out[landmark_id * 16 +: 16] <= y_in;
                if (count == 20) begin
                    frame_ready <= 1;
                    count <= 0;
                end
                else begin
                    count <= count + 1;
                end
            end
        end
    end

endmodule