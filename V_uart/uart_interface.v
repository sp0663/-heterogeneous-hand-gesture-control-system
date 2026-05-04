`timescale 1ns / 1ps

module uart_interface (
    input clk,
    input reset,
    input rx,           // Pmod RX pin JA2 (From PC)
    output tx,          // Pmod TX pin JA3 (To PC)
    
    // RX Stream (To HFT Core)
    output [7:0] rx_data,
    output rx_valid,    
    
    // TX Stream (From HFT Core)
    input [7:0] tx_data,
    input tx_valid      
);

    wire tick;
    wire rx_done_tick, tx_done_tick;
    wire [7:0] rx_raw_data, tx_fifo_out;
    wire rx_empty, tx_empty;

    // 1. Baud Rate Generator (115200 @ 100MHz -> M=54)
    baud_rate_generator #(.M(54), .N(6)) BAUDRATE_GEN (
        .clk(clk), .reset(reset), .tick(tick)
    );

    // 2. UART Receiver
    uart_receiver RX_UNIT (
        .clk(clk), .reset(reset), .rx(rx), .sample_tick(tick),
        .data_ready(rx_done_tick), .data_out(rx_raw_data)
    );

    // 3. RX FIFO: Buffers bursty market data from the PC
    assign rx_valid = ~rx_empty; 
    
    fifo #(.DATA_SIZE(8), .ADDR_SPACE_EXP(4)) RX_FIFO (
        .clk(clk), .reset(reset),
        .write_to_fifo(rx_done_tick), 
        .read_from_fifo(rx_valid), 
        .write_data_in(rx_raw_data),
        .read_data_out(rx_data),
        .empty(rx_empty),
        .full()
    );

    // 4. TX FIFO: Buffers responses (e.g. Best Bid) from the HFT Core
    fifo #(.DATA_SIZE(8), .ADDR_SPACE_EXP(4)) TX_FIFO (
        .clk(clk), .reset(reset),
        .write_to_fifo(tx_valid),       // Core pulses this to save a byte
        .read_from_fifo(tx_done_tick),  // TX Unit pulses this when finished sending
        .write_data_in(tx_data),
        .read_data_out(tx_fifo_out),
        .empty(tx_empty),
        .full()
    );

    // 5. UART Transmitter
    uart_transmitter TX_UNIT (
        .clk(clk), .reset(reset),
        .tx_start(~tx_empty),           // Transmit whenever TX FIFO has data
        .sample_tick(tick),
        .data_in(tx_fifo_out),
        .tx_done(tx_done_tick),
        .tx(tx)
    );

endmodule
