`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 07.02.2026 10:49:05
// Design Name: 
// Module Name: fifo
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

module fifo
#(
    parameter DATA_SIZE = 8,
    parameter ADDR_SPACE_EXP = 4 // 2^4 = 16 words depth (Increase this later for HFT)
)
(
    input clk,
    input reset,
    input write_to_fifo,
    input read_from_fifo,
    input [DATA_SIZE-1:0] write_data_in,
    output [DATA_SIZE-1:0] read_data_out,
    output empty,
    output full
);
    reg [DATA_SIZE-1:0] memory [2**ADDR_SPACE_EXP-1:0];
    reg [ADDR_SPACE_EXP-1:0] current_write_addr, next_write_addr;
    reg [ADDR_SPACE_EXP-1:0] current_read_addr, next_read_addr;
    reg full_reg, empty_reg, full_next, empty_next;

    always @(posedge clk)
        if(write_to_fifo && !full_reg)
            memory[current_write_addr] <= write_data_in;

    always @(posedge clk, posedge reset)
        if(reset) begin
            current_write_addr <= 0;
            current_read_addr <= 0;
            full_reg <= 1'b0;
            empty_reg <= 1'b1;
        end else begin
            current_write_addr <= next_write_addr;
            current_read_addr <= next_read_addr;
            full_reg <= full_next;
            empty_reg <= empty_next;
        end

    always @* begin
        next_write_addr = current_write_addr;
        next_read_addr = current_read_addr;
        full_next = full_reg;
        empty_next = empty_reg;

        case({write_to_fifo, read_from_fifo})
            2'b10: // Write
                if(!full_reg) begin
                    next_write_addr = current_write_addr + 1;
                    empty_next = 1'b0;
                    if(next_write_addr == current_read_addr)
                        full_next = 1'b1;
                end
            2'b01: // Read
                if(!empty_reg) begin
                    next_read_addr = current_read_addr + 1;
                    full_next = 1'b0;
                    if(next_read_addr == current_write_addr)
                        empty_next = 1'b1;
                end
            2'b11: // Write and Read
                begin
                    next_write_addr = current_write_addr + 1;
                    next_read_addr = current_read_addr + 1;
                end
        endcase
    end

    assign read_data_out = memory[current_read_addr];
    assign full = full_reg;
    assign empty = empty_reg;
endmodule