// Computes whether the angle between two vectors formed by three landmarks
// exceeds 160 degrees using dot product comparison with hysteresis (120-160 deg).
// No division — comparison is rearranged to use only multiplications.
//
// angle > 160 deg  iff  dot < 0  AND  dot^2 * 8192 > 7234 * mag1_sq * mag2_sq
// angle < 150 deg  iff  dot > 0  OR   dot^2 * 8192 < 2048 * mag1_sq * mag2_sq
//
// Pipeline (5 cycles latency):
//   Stage 1 : subtract → get vectors vx1,vy1,vx2,vy2
//   Stage 2 : multiply → dot, mag1_sq, mag2_sq
//   Stage 3 : multiply → mag_prod, lhs  (dot^2 * 8192)
//   Stage 4 : multiply → rhs_160, rhs_150
//   Stage 5 : compare  → finger_extended

module angle_calculator (
    input clk,
    input rst,
    input valid_in,

    input [15:0] x1, y1,   // first point
    input [15:0] x2, y2,   // middle point (vertex)
    input [15:0] x3, y3,   // third point

    output reg finger_extended,
    output reg valid_out
);

    // ----------------------------------------------------------
    // Stage 1 — vector subtraction
    // ----------------------------------------------------------
    reg signed [16:0] vx1, vy1, vx2, vy2;
    reg valid_s1;

    always @(posedge clk) begin
        if (rst) begin
            vx1      <= 0; vy1 <= 0;
            vx2      <= 0; vy2 <= 0;
            valid_s1 <= 0;
        end else begin
            vx1      <= $signed({1'b0, x1}) - $signed({1'b0, x2});
            vy1      <= $signed({1'b0, y1}) - $signed({1'b0, y2});
            vx2      <= $signed({1'b0, x3}) - $signed({1'b0, x2});
            vy2      <= $signed({1'b0, y3}) - $signed({1'b0, y2});
            valid_s1 <= valid_in;
        end
    end

    // ----------------------------------------------------------
    // Stage 2 — dot product and magnitude squares
    // ----------------------------------------------------------
    reg signed [34:0] dot;
    reg        [34:0] mag1_sq, mag2_sq;
    reg valid_s2;

    always @(posedge clk) begin
        if (rst) begin
            dot      <= 0;
            mag1_sq  <= 0;
            mag2_sq  <= 0;
            valid_s2 <= 0;
        end else begin
            dot      <= vx1 * vx2 + vy1 * vy2;
            mag1_sq  <= vx1 * vx1 + vy1 * vy1;
            mag2_sq  <= vx2 * vx2 + vy2 * vy2;
            valid_s2 <= valid_s1;
        end
    end

    // ----------------------------------------------------------
    // Stage 3 — mag_prod and lhs
    // ----------------------------------------------------------
    reg [69:0]  mag_prod;
    reg [82:0]  lhs;
    reg valid_s3;

    always @(posedge clk) begin
        if (rst) begin
            mag_prod <= 0;
            lhs      <= 0;
            valid_s3 <= 0;
        end else begin
            mag_prod <= mag1_sq * mag2_sq;
            lhs      <= (dot * dot) * 83'd8192;
            valid_s3 <= valid_s2;
        end
    end

    // ----------------------------------------------------------
    // Stage 4 — rhs thresholds
    // ----------------------------------------------------------
    reg [82:0] rhs_160, rhs_150;
    reg [82:0] lhs_r;
    reg valid_s4;

    always @(posedge clk) begin
        if (rst) begin
            rhs_160  <= 0;
            rhs_150  <= 0;
            lhs_r    <= 0;
            valid_s4 <= 0;
        end else begin
            rhs_160  <= 83'd7234 * mag_prod;
            rhs_150  <= 83'd6144 * mag_prod;
            lhs_r    <= lhs;        // keep lhs aligned with rhs
            valid_s4 <= valid_s3;
        end
    end

    // Also need dot sign aligned to Stage 4 — pipeline it through s3→s4
    reg dot_neg_s3, dot_neg_s4;
    always @(posedge clk) begin
        if (rst) begin
            dot_neg_s3 <= 0;
            dot_neg_s4 <= 0;
        end else begin
            dot_neg_s3 <= dot[34];      // sign bit of dot (Stage 2 output)
            dot_neg_s4 <= dot_neg_s3;
        end
    end

    // ----------------------------------------------------------
    // Stage 5 — compare and output with hysteresis
    // ----------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            finger_extended <= 0;
            valid_out       <= 0;
        end else begin
            valid_out <= valid_s4;
            if (valid_s4) begin
                if (dot_neg_s4 && lhs_r > rhs_160)
                    finger_extended <= 1;           // angle > 160 deg
                else if (!dot_neg_s4 || lhs_r < rhs_150)
                    finger_extended <= 0;           // angle < 150 deg
                // else: hysteresis — keep previous value
            end
        end
    end

endmodule