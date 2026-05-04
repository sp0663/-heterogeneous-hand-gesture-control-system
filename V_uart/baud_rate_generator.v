`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 07.02.2026 10:49:05
// Design Name: 
// Module Name: baud_rate_generator
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


module baud_rate_generator
#(
    parameter N = 6,     // Bits needed to store 54 (2^6 = 64)
    parameter M = 54     // Calculated for 115200 baud @ 100MHz
)
(
    input clk,
    input reset,
    output tick          // Generates a tick 16 times per bit
);
    reg [N-1:0] counter;
    wire [N-1:0] next;

    always @(posedge clk, posedge reset)
        if(reset)
            counter <= 0;
        else
            counter <= next;

    assign next = (counter == (M-1)) ? 0 : counter + 1;
    assign tick = (counter == (M-1)) ? 1'b1 : 1'b0;
endmodule
