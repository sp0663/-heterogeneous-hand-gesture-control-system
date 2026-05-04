// Instantiates the feature extractor and applies rule-based gesture classification on the computed features.
// Static gestures: PINCH, FIST, OPEN_HAND, INDEX_FINGER.
// Dynamic gestures: PINCH_CW, PINCH_ACW — detected by tracking the pinch-point
// vector (midpoint of thumb-tip and index-tip, relative to the wrist) across
// successive pinch frames and accumulating its signed cross product (proxy for
// sin(delta_theta)). Mirrors the reference controller's rotation-accumulator
// scheme in gesture_recogniser.py.


module gesture_classifier (
    input clk,
    input rst,
    input valid_in,

    input [335:0] x,
    input [335:0] y,

    output reg [2:0] gesture_id,
    output reg valid_out
);
    localparam PINCH        = 3'b000,
               FIST         = 3'b001,
               OPEN_HAND    = 3'b010,
               INDEX_FINGER = 3'b011,
               UNKNOWN      = 3'b100,
               PINCH_CW     = 3'b101,
               PINCH_ACW    = 3'b110;

    // Rotation accumulator tuning.
    // cross_scaled ~ sin(d_theta) * |v|^2 / 2^CROSS_SHIFT, where |v| is the
    // pinch-vector magnitude in doubled units (see dx_curr below). For a
    // typical pinch pose |v_doubled| lands around 32000 in the landmark-capture
    // normalisation, so 1 degree of rotation yields ~1 unit with CROSS_SHIFT=24
    // and ACC_THRESH=10 matches the reference's 10-degree trigger threshold.
    // NOISE_FLOOR mirrors Python's |delta|>1.5 gate, preventing per-frame
    // landmark jitter from random-walking the accumulator into false triggers.
    localparam integer       CROSS_SHIFT = 24;
    localparam signed [31:0] ACC_THRESH  = 32'sd10;
    localparam signed [31:0] NOISE_FLOOR = 32'sd2;

    wire [32:0] dist_thumb_index;
    wire [32:0] dist_wrist_middle;

    wire thumb_extended;
    wire index_extended;
    wire middle_extended;
    wire ring_extended;
    wire pinky_extended;

    wire thumb_angle_valid;
    wire index_angle_valid;
    wire middle_angle_valid;
    wire ring_angle_valid;
    wire pinky_angle_valid;
    wire all_angle_valid = thumb_angle_valid & index_angle_valid & middle_angle_valid & ring_angle_valid & pinky_angle_valid;

    reg valid_in_1, valid_in_2, valid_in_3, valid_in_4, valid_in_5;  // Delayed versions of valid_in for timing alignment

    feature_extractor features (
        .clk(clk),
        .rst(rst),
        .valid_in(valid_in),

        .x(x),
        .y(y),

        .dist_thumb_index(dist_thumb_index),
        .dist_wrist_middle(dist_wrist_middle),

        .thumb_extended(thumb_extended),
        .index_extended(index_extended),
        .middle_extended(middle_extended),
        .ring_extended(ring_extended),
        .pinky_extended(pinky_extended),

        .thumb_angle_valid(thumb_angle_valid),
        .index_angle_valid(index_angle_valid),
        .middle_angle_valid(middle_angle_valid),
        .ring_angle_valid(ring_angle_valid),
        .pinky_angle_valid(pinky_angle_valid)
    );

    always @(posedge clk) begin
        if (rst) begin
            valid_in_1 <= 0;
            valid_in_2 <= 0;
            valid_in_3 <= 0;
            valid_in_4 <= 0;
            valid_in_5 <= 0;
        end else begin
            valid_in_1 <= valid_in;
            valid_in_2 <= valid_in_1;
            valid_in_3 <= valid_in_2;
            valid_in_4 <= valid_in_3;
            valid_in_5 <= valid_in_4;
        end
    end

    // ------------------------------------------------------------------
    // Pinch-rotation tracking
    // Pinch-point := (thumb_tip + index_tip) / 2. To avoid losing a bit of
    // precision from the right-shift we keep the factor of two and work with
    //   dx = (thumb_x + index_x) - 2*wrist_x   (== 2 * (pinch_cx - wrist_x))
    //   dy = (thumb_y + index_y) - 2*wrist_y
    // The factor is common to prev and curr frames so it rescales the
    // accumulator but leaves the cross-product sign (rotation direction)
    // untouched.
    // ------------------------------------------------------------------

    wire [15:0] wrist_x = x[0 * 16 +: 16];
    wire [15:0] wrist_y = y[0 * 16 +: 16];
    wire [15:0] thumb_x = x[4 * 16 +: 16];
    wire [15:0] thumb_y = y[4 * 16 +: 16];
    wire [15:0] index_x = x[8 * 16 +: 16];
    wire [15:0] index_y = y[8 * 16 +: 16];

    wire [16:0] sum_x       = {1'b0, thumb_x} + {1'b0, index_x};
    wire [16:0] sum_y       = {1'b0, thumb_y} + {1'b0, index_y};
    wire [16:0] two_wrist_x = {wrist_x, 1'b0};
    wire [16:0] two_wrist_y = {wrist_y, 1'b0};

    wire signed [18:0] dx_curr = $signed({2'b00, sum_x}) - $signed({2'b00, two_wrist_x});
    wire signed [18:0] dy_curr = $signed({2'b00, sum_y}) - $signed({2'b00, two_wrist_y});

    reg  signed [18:0] prev_dx, prev_dy;
    reg                prev_pinch_valid;
    reg  signed [31:0] rotation_accumulator;

    // Explicit sign-extended products avoid any self-determined-width surprises
    // when the 19-bit signed operands feed a wider result wire.
    wire signed [37:0] prod1        = prev_dx * dy_curr;
    wire signed [37:0] prod2        = dx_curr * prev_dy;
    wire signed [37:0] cross_raw    = prod1 - prod2;
    wire signed [31:0] cross_scaled = cross_raw >>> CROSS_SHIFT;

    // Noise gate: below NOISE_FLOOR the cross product is indistinguishable
    // from MediaPipe landmark jitter, so treat it as zero rotation. Without
    // this, a stationary pinch would slowly drift the accumulator over many
    // frames and eventually fire a spurious CW/ACW.
    wire signed [31:0] cross_abs       = cross_scaled[31] ? -cross_scaled : cross_scaled;
    wire               cross_above_nf  = (cross_abs >= NOISE_FLOOR);
    wire signed [31:0] cross_effective = cross_above_nf ? cross_scaled : 32'sd0;
    wire signed [31:0] acc_next        = rotation_accumulator + cross_effective;

    wire is_pinch = (dist_thumb_index * 16 < dist_wrist_middle);

    always @(posedge clk) begin
        if (rst) begin
            gesture_id           <= 0;
            valid_out            <= 0;
            prev_dx              <= 0;
            prev_dy              <= 0;
            prev_pinch_valid     <= 0;
            rotation_accumulator <= 0;
        end
        else begin
            valid_out <= 0;
            if (valid_in_5 && all_angle_valid) begin
                valid_out <= 1;
                if (is_pinch) begin
                    // Capture current pinch vector for next frame.
                    prev_dx          <= dx_curr;
                    prev_dy          <= dy_curr;
                    prev_pinch_valid <= 1;

                    if (!prev_pinch_valid) begin
                        // First pinch frame after a non-pinch: no previous
                        // vector to compare against, so just report static
                        // pinch and let the next frame start accumulating.
                        gesture_id <= PINCH;
                    end
                    else if (acc_next > ACC_THRESH) begin
                        gesture_id           <= PINCH_CW;
                        rotation_accumulator <= acc_next - ACC_THRESH;
                    end
                    else if (acc_next < -ACC_THRESH) begin
                        gesture_id           <= PINCH_ACW;
                        rotation_accumulator <= acc_next + ACC_THRESH;
                    end
                    else begin
                        gesture_id           <= PINCH;
                        rotation_accumulator <= acc_next;
                    end
                end
                else begin
                    // Non-pinch: drop the running pinch-vector reference so the
                    // next pinch starts fresh. rotation_accumulator is kept,
                    // matching gesture_recogniser.py which only clears
                    // prev_angle/locked_hand_type in its else-branch.
                    prev_pinch_valid <= 0;

                    if (!index_extended && !middle_extended && !ring_extended && !pinky_extended) begin
                        gesture_id <= FIST;
                    end
                    else if (thumb_extended && index_extended && middle_extended && ring_extended && pinky_extended) begin
                        gesture_id <= OPEN_HAND;
                    end
                    else if (index_extended && !middle_extended && !ring_extended && !pinky_extended) begin
                        gesture_id <= INDEX_FINGER;
                    end
                    else begin
                        gesture_id <= UNKNOWN;
                    end
                end
            end
        end
    end


endmodule
