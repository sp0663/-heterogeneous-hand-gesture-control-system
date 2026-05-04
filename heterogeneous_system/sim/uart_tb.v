`timescale 1ns / 1ps

module uart_top_tb();

    reg clk_50MHz, reset, rx, write_uart;
    reg [7:0] write_data;
    wire tx, frame_ready;
    wire [335:0] landmarks_x;
    wire [335:0] landmarks_y;
    integer j;
    // 50MHz Clock Generation (20ns period)
    always #10 clk_50MHz = ~clk_50MHz;

    // Instantiate the Top Module
    uart_top #(
        .BR_LIMIT(27),
        .FIFO_EXP(7)
    ) dut (
        .clk_50MHz(clk_50MHz),
        .reset(reset),
        .rx(rx),
        .write_data(write_data),
        .write_uart(write_uart),
        .tx(tx),
        .frame_ready(frame_ready),
        .landmarks_x(landmarks_x),
        .landmarks_y(landmarks_y)
    );

    // UART Transmit Task (Calculated for 50MHz, BR_LIMIT=27, 16 Oversampling)
    task send_byte(input [7:0] data);
        integer i;
        begin
            // Send Start Bit (0)
            rx = 0;
            #(432 * 20); 
            // Send 8 Data Bits (LSB First)
            for (i = 0; i < 8; i = i + 1) begin
                rx = data[i];
                #(432 * 20);
            end
            // Send Stop Bit (1)
            rx = 1;
            #(432 * 20);
        end
    endtask

    initial begin
        $dumpfile("uart_sim.vcd");
        $dumpvars(0, uart_top_tb);

        // 1. Initialization
        clk_50MHz = 0;
        reset = 1;
        rx = 1; // UART Idle state is High
        write_uart = 0;
        write_data = 0;

        #200 reset = 0; 
        #1000; 

        // 2. Send Landmark 0 (ID = 0, X = 0x1122, Y = 0x3344)
        $display("[%0t] Sending Landmark 0", $time);
        send_byte(8'h00);   // ID = 0
        send_byte(8'h11);   // X High
        send_byte(8'h22);   // X Low
        send_byte(8'h33);   // Y High
        send_byte(8'h44);   // Y Low

        // 3. Send Landmark 1 (ID = 1, X = 0x5566, Y = 0x7788)
        $display("[%0t] Sending Landmark 1", $time);
        send_byte(8'h01);   // ID = 1
        send_byte(8'h55);   // X High
        send_byte(8'h66);   // X Low
        send_byte(8'h77);   // Y High
        send_byte(8'h88);   // Y Low

        // Send Landmark 2 (ID = 2, X = 0x99AA, Y = 0xBBCC)
        send_byte(8'h02);   // ID = 2
        send_byte(8'h99);   // X High
        send_byte(8'hAA);   // X Low
        send_byte(8'hBB);   // Y High
        send_byte(8'hCC);   // Y Low

        //Send Landmark 3 (ID = 3, X = 0xDDEE, Y = 0xFF00)
        send_byte(8'h03);   // ID = 3
        send_byte(8'hDD);   // X High
        send_byte(8'hEE);   // X Low
        send_byte(8'hFF);   // Y High
        send_byte(8'h00);   // Y Low

        //Send Landmark 4 (ID = 4, X = 0x1234, Y = 0x5678)
        send_byte(8'h04);   // ID = 4
        send_byte(8'h12);   // X High
        send_byte(8'h34);   // X Low
        send_byte(8'h56);   // Y High
        send_byte(8'h78);   // Y Low

        //Send Landmark 5 (ID = 5, X = 0x9ABC, Y = 0xDEF0)
        send_byte(8'h05);   // ID = 5
        send_byte(8'h9A);   // X High
        send_byte(8'hBC);   // X Low
        send_byte(8'hDE);   // Y High
        send_byte(8'hF0);   // Y Low

        //21 landmarks total, so send 16 more with dummy data
        
        for (j = 6; j < 21; j = j + 1) begin
            send_byte(j);   // ID = j
            send_byte(8'hAA);   // X High
            send_byte(8'h30);   // X Low
            send_byte(8'hDE);   // Y High
            send_byte(8'h10);   // Y Low
        end

        // 4. Wait for processing to clear
        #100000;
        
        $display("=== SIMULATION RESULTS ===");
        $display("X (Bits 15:0):  %h (Expected: 1122)", dut.STORAGE_UNIT.x_out[15:0]);
        $display("Y (Bits 15:0):  %h (Expected: 3344)", dut.STORAGE_UNIT.y_out[15:0]);
        $display("X[10] (Bits 31:16): %h (Expected: 5566)", dut.STORAGE_UNIT.x_out[31:16]);
        $display("Y[10] (Bits 31:16): %h (Expected: 7788)", dut.STORAGE_UNIT.y_out[31:16]);
        $display("[%0t] Simulation Finished", $time);
        $finish;
    end
endmodule