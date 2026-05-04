`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 07.02.2026 10:49:05
// Design Name: 
// Module Name: uart_transmitter
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module uart_transmitter
#(
    parameter DBITS = 8,          // Number of data bits (8N1)
    parameter SB_TICK = 16        // 16 ticks = 1 Stop Bit width
)
(
    input clk,                    // 100MHz System Clock
    input reset,                  // Active High Reset
    input tx_start,               // Pulse to start transmission (from FIFO)
    input sample_tick,            // 16x Baud Tick from Baud Generator
    input [DBITS-1:0] data_in,    // Byte to transmit
    output reg tx_done,           // Pulses High when transmission finishes
    output tx                     // Serial Data Output (Wire to PC)
);

    // --- State Machine Encoding ---
    localparam [1:0] 
        idle  = 2'b00,
        start = 2'b01,
        data  = 2'b10,
        stop  = 2'b11;

    // --- Registers ---
    reg [1:0] state, next_state;       // FSM State
    reg [3:0] tick_reg, tick_next;     // Counts 0-15 for oversampling
    reg [2:0] nbits_reg, nbits_next;   // Counts 0-7 for Data Bits
    reg [DBITS-1:0] data_reg, data_next; // Shift register for the byte
    reg tx_reg, tx_next;               // Output buffer to prevent glitches

    // --- Sequential Logic (Clocked) ---
    always @(posedge clk, posedge reset) begin
        if (reset) begin
            state <= idle;
            tick_reg <= 0;
            nbits_reg <= 0;
            data_reg <= 0;
            tx_reg <= 1'b1; // UART Idle is High
        end else begin
            state <= next_state;
            tick_reg <= tick_next;
            nbits_reg <= nbits_next;
            data_reg <= data_next;
            tx_reg <= tx_next;
        end
    end

    // --- Combinational Logic (Next State) ---
    always @* begin
        // Default assignments (Hold state)
        next_state = state;
        tx_done = 1'b0;
        tick_next = tick_reg;
        nbits_next = nbits_reg;
        data_next = data_reg;
        tx_next = tx_reg;

        case (state)
            // 1. IDLE: Wait for tx_start signal
            idle: begin
                tx_next = 1'b1; // Drive Line High (Idle)
                if (tx_start) begin
                    next_state = start;
                    tick_next = 0;
                    data_next = data_in; // Load data from FIFO
                end
            end

            // 2. START BIT: Drive Low for 16 ticks
            start: begin
                tx_next = 1'b0; 
                if (sample_tick) begin
                    if (tick_reg == 15) begin
                        next_state = data;
                        tick_next = 0;
                        nbits_next = 0;
                    end else begin
                        tick_next = tick_reg + 1;
                    end
                end
            end

            // 3. DATA BITS: Shift out 8 bits (LSB First)
            data: begin
                tx_next = data_reg; // Send LSB
                if (sample_tick) begin
                    if (tick_reg == 15) begin
                        tick_next = 0;
                        data_next = data_reg >> 1; // Shift Right
                        if (nbits_reg == (DBITS - 1)) begin
                            next_state = stop;
                        end else begin
                            nbits_next = nbits_reg + 1;
                        end
                    end else begin
                        tick_next = tick_reg + 1;
                    end
                end
            end

            // 4. STOP BIT: Drive High for 16 ticks
            stop: begin
                tx_next = 1'b1; // Drive Line High
                if (sample_tick) begin
                    if (tick_reg == (SB_TICK - 1)) begin
                        next_state = idle;
                        tx_done = 1'b1; // Signal 'Done' to pop FIFO
                    end else begin
                        tick_next = tick_reg + 1;
                    end
                end
            end
        endcase
    end

    // Assign Output
    assign tx = tx_reg;

endmodule
