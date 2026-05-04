`timescale 1ns / 1ps

// ============================================================
//  Testbench : gesture_system_top
//
//  Clock  : 50 MHz  (T = 20 ns)
//  UART   : 115200 baud, 8-N-1
//  Baud-rate generator M=27  →  one bit = 27 * 20 ns = 540 ns
//  One UART byte ≈ 27 * 16 * (1+8+1) × 20 ns ≈ 86.4 µs
//
//  Packet format (5 bytes per landmark, 21 landmarks per frame):
//    byte 0 : landmark id   [7:0]  (only [4:0] used)
//    byte 1 : x_high        [15:8]
//    byte 2 : x_low         [ 7:0]
//    byte 3 : y_high        [15:8]
//    byte 4 : y_low         [ 7:0]
//
//  Test cases (one frame each):
//    1. OPEN_HAND     – all fingers extended
//    2. FIST          – all fingers curled
//    3. INDEX_FINGER  – only index extended
//    4. PINCH         – thumb-tip near index-tip
//    5. UNKNOWN       – mixed state
// ============================================================

module gesture_system_top_tb;

    // --------------------------------------------------------
    // Parameters
    // --------------------------------------------------------
    localparam CLK_PERIOD   = 10;          // ns  (50 MHz)
    localparam BAUD_TICKS   = 27;          // baud generator M
    localparam OS_TICKS     = 16;          // oversampling ratio
    // One UART bit period in ns:
    localparam BIT_PERIOD   = BAUD_TICKS * OS_TICKS * CLK_PERIOD * 2; // 8640 ns

    // Expected gesture IDs (must match gesture_classifier.v)
    localparam PINCH        = 3'b000;
    localparam FIST         = 3'b001;
    localparam OPEN_HAND    = 3'b010;
    localparam INDEX_FINGER = 3'b011;
    localparam UNKNOWN      = 3'b100;

    // --------------------------------------------------------
    // DUT signals
    // --------------------------------------------------------
    reg  clk = 0;
    reg  rst = 1;
    reg  rx  = 1;          // idle-high
    wire tx;

    // --------------------------------------------------------
    // Instantiate DUT
    // --------------------------------------------------------
    gesture_system_top dut (
        .clk_100MHz (clk),   // tb drives 100MHz
        .rst        (rst),
        .rx         (rx),
        .tx         (tx)
    );

    // --------------------------------------------------------
    // Clock generator
    // --------------------------------------------------------
    always #(CLK_PERIOD/2) clk = ~clk;

    // --------------------------------------------------------
    // Scoreboard / result capture
    // --------------------------------------------------------
    integer pass_count = 0;
    integer fail_count = 0;

    // Monitor the TX line and decode the returned gesture byte
    // The DUT sends a byte via UART whenever gesture_valid fires.
    // We capture it and compare against the expected value.

    reg [7:0] rx_capture;
    reg       rx_captured = 0;

    task automatic uart_receive_byte;
        output [7:0] data;
        integer i;
        begin
            // Wait for start bit (TX goes low)
            @(negedge tx);
            // Sample mid-point of start bit
            #(BIT_PERIOD / 2);
            // Verify it really is a start bit
            if (tx !== 1'b0) begin
                $display("  [RX] ERROR: false start bit detected");
                data = 8'hxx;
            end else begin
                #BIT_PERIOD; // skip start bit
                for (i = 0; i < 8; i = i + 1) begin
                    data[i] = tx;
                    #BIT_PERIOD;
                end
                // Stop bit
                if (tx !== 1'b1)
                    $display("  [RX] WARNING: stop bit is not 1 (got %b)", tx);
            end
        end
    endtask

    // --------------------------------------------------------
    // UART transmit task – send one byte to the DUT (RX line)
    // 8-N-1, LSB first
    // --------------------------------------------------------
    task automatic uart_send_byte;
        input [7:0] data;
        integer i;
        begin
            // Start bit
            rx = 1'b0;
            #BIT_PERIOD;
            // Data bits LSB first
            for (i = 0; i < 8; i = i + 1) begin
                rx = data[i];
                #BIT_PERIOD;
            end
            // Stop bit
            rx = 1'b1;
            #BIT_PERIOD;
        end
    endtask

    // --------------------------------------------------------
    // Send one complete landmark (5 bytes)
    // --------------------------------------------------------
    task automatic send_landmark;
        input [4:0] id;
        input [15:0] x;
        input [15:0] y;
        begin
            uart_send_byte({3'b000, id});   // id byte
            uart_send_byte(x[15:8]);         // x high
            uart_send_byte(x[7:0]);          // x low
            uart_send_byte(y[15:8]);         // y high
            uart_send_byte(y[7:0]);          // y low
        end
    endtask

    // --------------------------------------------------------
    // Send a full frame of 21 landmarks
    // Arrays: ids 0-20, x[0..20], y[0..20]
    // --------------------------------------------------------
    task automatic send_frame;
        input [335:0] xs;   // packed [id*16 +: 16]
        input [335:0] ys;
        integer lm;
        begin
            for (lm = 0; lm < 21; lm = lm + 1) begin
                send_landmark(
                    lm[4:0],
                    xs[lm*16 +: 16],
                    ys[lm*16 +: 16]
                );
            end
        end
    endtask

    // --------------------------------------------------------
    // Check helper
    // --------------------------------------------------------
    task automatic check_gesture;
        input [2:0] expected;
        input [63:0] test_name; // 8-char string packed
        reg [7:0] received;
        begin
            // Wait up to 30 ms for the TX byte (very generous)
            fork
                begin : wait_for_result
                    uart_receive_byte(received);
                    disable timeout_watch;
                end
                begin : timeout_watch
                    #30_000_000;
                    $display("  [TIMEOUT] No TX response for test '%s'", test_name);
                    received = 8'hff;
                    disable wait_for_result;
                end
            join

            if (received[2:0] === expected) begin
                $display("  [PASS] %-12s  expected=%0d  got=%0d",
                         test_name, expected, received[2:0]);
                pass_count = pass_count + 1;
            end else begin
                $display("  [FAIL] %-12s  expected=%0d  got=%0d",
                         test_name, expected, received[2:0]);
                fail_count = fail_count + 1;
            end
        end
    endtask

    // ========================================================
    // Landmark coordinate helpers
    //
    //  MediaPipe wrist = 0, thumb tip = 4, index tip = 8,
    //  middle tip = 12, ring tip = 16, pinky tip = 20.
    //
    //  Finger knuckle/mid sets used by angle_calculator:
    //    thumb  : 2-3-4
    //    index  : 5-6-7
    //    middle : 9-10-11
    //    ring   : 13-14-15
    //    pinky  : 17-18-19
    //
    //  Coordinates are 16-bit unsigned (pixel-like).
    //
    //  Strategy for "extended" finger:
    //    Place three landmarks so the angle at the middle point
    //    is > 160 degrees (nearly straight).
    //    e.g.  p1=(100,200), p2=(100,150), p3=(100,100) → 180°
    //
    //  Strategy for "curled" finger:
    //    Angle < 120° (e.g. L-shape).
    //    e.g.  p1=(100,150), p2=(100,100), p3=(150,100) → 90°
    //
    //  dist_wrist_middle is compared to dist_thumb_index * 16.
    //  For PINCH: dist_thumb_index must be very small so that
    //             dist_thumb_index * 16 < dist_wrist_middle
    // ========================================================

    // Build packed landmark arrays
    reg [335:0] xs, ys;

    // Helper macro-task to set one landmark
    task set_lm;
        input [4:0] id;
        input [15:0] x;
        input [15:0] y;
        begin
            xs[id*16 +: 16] = x;
            ys[id*16 +: 16] = y;
        end
    endtask

    // --------------------------------------------------------
    // Build OPEN_HAND frame:
    //   All fingers straight (angle > 160°)
    //   wrist → middle baseline large (thumb-index far)
    // --------------------------------------------------------
    task build_open_hand;
        integer i;
        begin
            xs = 0; ys = 0;
            // Wrist at (200, 400)
            set_lm(0,  200, 400);
            // Thumb CMC/base  lm1
            set_lm(1,  170, 380);
            // Thumb  2-3-4 straight (going upper-left at angle > 160°)
            set_lm(2,  160, 360);
            set_lm(3,  150, 340);
            set_lm(4,  140, 320);   // thumb tip
            // Index base lm5,6,7 straight up
            set_lm(5,  200, 350);
            set_lm(6,  200, 300);
            set_lm(7,  200, 250);   // index tip  lm8 below
            set_lm(8,  200, 200);
            // Middle base lm9,10,11 straight up
            set_lm(9,  220, 350);
            set_lm(10, 220, 300);
            set_lm(11, 220, 250);   // middle tip lm12 below
            set_lm(12, 220, 200);
            // Ring base lm13,14,15 straight up
            set_lm(13, 240, 350);
            set_lm(14, 240, 300);
            set_lm(15, 240, 250);   // ring tip   lm16 below
            set_lm(16, 240, 200);
            // Pinky base lm17,18,19 straight up
            set_lm(17, 260, 350);
            set_lm(18, 260, 300);
            set_lm(19, 260, 250);   // pinky tip  lm20 below
            set_lm(20, 260, 200);
        end
    endtask

    // --------------------------------------------------------
    // Build FIST frame:
    //   All fingers curled (angle < 120° at each mid joint)
    // --------------------------------------------------------
    task build_fist;
        begin
            xs = 0; ys = 0;
            set_lm(0,  200, 400);   // wrist
            set_lm(1,  180, 380);
            // Thumb  2-3-4 → 90° bend
            set_lm(2,  160, 360);
            set_lm(3,  160, 340);   // goes straight up then...
            set_lm(4,  180, 340);   // ...turns right → 90°
            // Index  5-6-7 → curled
            set_lm(5,  200, 360);
            set_lm(6,  200, 340);
            set_lm(7,  220, 340);   // 90° bend
            set_lm(8,  220, 360);   // tip curls back
            // Middle 9-10-11
            set_lm(9,  220, 360);
            set_lm(10, 220, 340);
            set_lm(11, 240, 340);
            set_lm(12, 240, 360);
            // Ring  13-14-15
            set_lm(13, 240, 360);
            set_lm(14, 240, 340);
            set_lm(15, 260, 340);
            set_lm(16, 260, 360);
            // Pinky 17-18-19
            set_lm(17, 260, 360);
            set_lm(18, 260, 340);
            set_lm(19, 280, 340);
            set_lm(20, 280, 360);
        end
    endtask

    // --------------------------------------------------------
    // Build INDEX_FINGER frame:
    //   Index extended, others curled
    // --------------------------------------------------------
    task build_index_finger;
        begin
            xs = 0; ys = 0;
            set_lm(0,  200, 400);   // wrist
            set_lm(1,  180, 380);
            // Thumb curled
            set_lm(2,  160, 360);
            set_lm(3,  160, 340);
            set_lm(4,  180, 340);
            // Index straight up (extended)
            set_lm(5,  200, 350);
            set_lm(6,  200, 300);
            set_lm(7,  200, 250);
            set_lm(8,  200, 200);
            // Middle curled
            set_lm(9,  220, 360);
            set_lm(10, 220, 340);
            set_lm(11, 240, 340);
            set_lm(12, 240, 360);
            // Ring curled
            set_lm(13, 240, 360);
            set_lm(14, 240, 340);
            set_lm(15, 260, 340);
            set_lm(16, 260, 360);
            // Pinky curled
            set_lm(17, 260, 360);
            set_lm(18, 260, 340);
            set_lm(19, 280, 340);
            set_lm(20, 280, 360);
        end
    endtask

    // --------------------------------------------------------
    // Build PINCH frame:
    //   Thumb tip (lm4) very close to index tip (lm8)
    //   Make dist_thumb_index*16 < dist_wrist_middle
    //
    //   dist_wrist_middle  = dist(lm0, lm12)²
    //   dist_thumb_index   = dist(lm4, lm8)²
    //
    //   Choose wrist=(200,400), middle=(200,200) → dist_sq=40000
    //   thumb tip=(200,300), index tip=(202,300) → dist_sq=4
    //   4*16=64 < 40000 → PINCH fires
    // --------------------------------------------------------
    task build_pinch;
        begin
            xs = 0; ys = 0;
            set_lm(0,  200, 400);   // wrist
            set_lm(1,  180, 380);
            set_lm(2,  160, 360);
            set_lm(3,  160, 340);
            set_lm(4,  200, 300);   // thumb tip (close to index tip)
            set_lm(5,  200, 350);
            set_lm(6,  200, 320);
            set_lm(7,  200, 310);
            set_lm(8,  202, 300);   // index tip  (2px from thumb tip)
            set_lm(9,  220, 350);
            set_lm(10, 220, 300);
            set_lm(11, 220, 250);
            set_lm(12, 220, 200);   // middle tip → far from wrist
            set_lm(13, 240, 350);
            set_lm(14, 240, 300);
            set_lm(15, 240, 250);
            set_lm(16, 240, 200);
            set_lm(17, 260, 350);
            set_lm(18, 260, 300);
            set_lm(19, 260, 250);
            set_lm(20, 260, 200);
        end
    endtask

    // --------------------------------------------------------
    // Build UNKNOWN frame:
    //   thumb + middle extended, index + ring + pinky curled
    // --------------------------------------------------------
    task build_unknown;
        begin
            xs = 0; ys = 0;
            set_lm(0,  200, 400);   // wrist
            set_lm(1,  180, 380);
            // Thumb straight
            set_lm(2,  160, 360);
            set_lm(3,  150, 340);
            set_lm(4,  140, 320);
            // Index curled
            set_lm(5,  200, 360);
            set_lm(6,  200, 340);
            set_lm(7,  220, 340);
            set_lm(8,  220, 360);
            // Middle straight
            set_lm(9,  220, 350);
            set_lm(10, 220, 300);
            set_lm(11, 220, 250);
            set_lm(12, 220, 200);
            // Ring curled
            set_lm(13, 240, 360);
            set_lm(14, 240, 340);
            set_lm(15, 260, 340);
            set_lm(16, 260, 360);
            // Pinky curled
            set_lm(17, 260, 360);
            set_lm(18, 260, 340);
            set_lm(19, 280, 340);
            set_lm(20, 280, 360);
        end
    endtask

    // ========================================================
    // Main test sequence
    // ========================================================
    integer test_num;

    initial begin
        $display("========================================");
        $display("  gesture_system_top testbench");
        $display("  Clock: 50 MHz  |  UART: 115200 baud");
        $display("========================================");

        // --------------------------------------------------
        // Reset
        // --------------------------------------------------
        rst = 1;
        rx  = 1;
        repeat(20) @(posedge clk);
        rst = 0;
        repeat(5) @(posedge clk);
        $display("[INFO] Reset released. Starting tests...\n");

        // ==================================================
        // TEST 1: OPEN_HAND
        // ==================================================
        $display("--- Test 1: OPEN_HAND (all fingers extended) ---");
        build_open_hand;
        send_frame(xs, ys);
        check_gesture(OPEN_HAND, "OPEN_HAND");
        $display("");

        // ==================================================
        // TEST 2: FIST
        // ==================================================
        $display("--- Test 2: FIST (all fingers curled) ---");
        build_fist;
        send_frame(xs, ys);
        check_gesture(FIST, "FIST     ");
        $display("");

        // ==================================================
        // TEST 3: INDEX_FINGER
        // ==================================================
        $display("--- Test 3: INDEX_FINGER (pointing) ---");
        build_index_finger;
        send_frame(xs, ys);
        check_gesture(INDEX_FINGER, "INDEX    ");
        $display("");

        // ==================================================
        // TEST 4: PINCH
        // ==================================================
        $display("--- Test 4: PINCH (thumb-tip near index-tip) ---");
        build_pinch;
        send_frame(xs, ys);
        check_gesture(PINCH, "PINCH    ");
        $display("");

        // ==================================================
        // TEST 5: UNKNOWN
        // ==================================================
        $display("--- Test 5: UNKNOWN (thumb+middle extended) ---");
        build_unknown;
        send_frame(xs, ys);
        check_gesture(UNKNOWN, "UNKNOWN  ");
        $display("");

        // ==================================================
        // TEST 6: Back-to-back frames (stress test)
        //   Two OPEN_HAND frames in a row – verifies that
        //   landmark_storage resets count correctly between frames.
        // ==================================================
        $display("--- Test 6a: Back-to-back OPEN_HAND (frame 1) ---");
        build_open_hand;
        send_frame(xs, ys);
        check_gesture(OPEN_HAND, "BB_OPEN_1");
        $display("--- Test 6b: Back-to-back OPEN_HAND (frame 2) ---");
        send_frame(xs, ys);
        check_gesture(OPEN_HAND, "BB_OPEN_2");
        $display("");

        // ==================================================
        // TEST 7: FIST after OPEN_HAND – checks no state bleed
        // ==================================================
        $display("--- Test 7: FIST after OPEN_HAND (no state bleed) ---");
        build_fist;
        send_frame(xs, ys);
        check_gesture(FIST, "FIST_2   ");
        $display("");

        // ==================================================
        // Summary
        // ==================================================
        $display("========================================");
        $display("  Results: %0d PASS  /  %0d FAIL", pass_count, fail_count);
        $display("========================================");

        if (fail_count == 0)
            $display("  ALL TESTS PASSED");
        else
            $display("  SOME TESTS FAILED – check waveform for details");

        $finish;
    end

    // ========================================================
    // Timeout watchdog – kill the sim if it hangs
    // ========================================================
    initial begin
        #500_000_000; // 500 ms simulation wall time
        $display("[WATCHDOG] Simulation timeout – force stop");
        $finish;
    end

    // ========================================================
    // VCD dump (remove/comment if not needed)
    // ========================================================
    initial begin
        $dumpfile("dmp.vcd");
        $dumpvars(0, gesture_system_top_tb);
    end

endmodule