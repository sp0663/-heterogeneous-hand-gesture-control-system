module uart_rx 
#( parameter DBITS = 8,
             SB_TICK= 16 //stop bit
)
(input clk_50MHz,
 input reset,
 input rx,
 input sample_tick,
 output reg data_ready,
 output [DBITS-1:0] data_out
) ;

localparam [1:0] idle = 2'b00,
                 start= 2'b01,
                 data = 2'b10,
                 stop = 2'b11;
reg [1:0] state,next_state;
reg [3:0] tick_reg, tick_next;
reg [2:0] nbits_reg, nbits_next;
reg [7:0] data_reg ,data_next;
reg rx_sync_1, rx_sync_2;
always @(posedge clk_50MHz) begin
    rx_sync_1 <= rx;
    rx_sync_2 <= rx_sync_1; 
end
//Register Logic
always @(posedge clk_50MHz, posedge reset) begin
    if (reset) begin
        state <= idle;
        tick_reg <= 0;
        nbits_reg <= 0;
        data_reg <= 0;
    end
    else begin
        state <= next_state;
        tick_reg <= tick_next;
        nbits_reg <= nbits_next;
        data_reg <= data_next;
    end
end
//State Machine logic
always@(*) begin
    next_state =state;
    data_ready =1'b0;
    tick_next = tick_reg;
    nbits_next = nbits_reg;
    data_next = data_reg;

    case(state)
        idle:begin
            if(~rx_sync_2) begin
                next_state = start;
                tick_next = 0;
            end
        end
        start: begin 
            if(sample_tick)begin
                if(tick_reg == 7) begin
                    next_state=data;
                    tick_next=0;
                    nbits_next=0;
                end
                else begin
                    tick_next = tick_reg + 1;
                end
            end
        end

        data: begin
            if(sample_tick) begin
                if(tick_reg == 15) begin
                    tick_next=0;
                    data_next={rx_sync_2,data_reg[7:1]};
                    if(nbits_reg == (DBITS-1))
                        next_state=stop;
                    else 
                        nbits_next=nbits_reg+1;
                end
                else    tick_next=tick_reg+1;
            end
        end
        stop:begin
            if(sample_tick) begin
                if(tick_reg == (SB_TICK-1)) begin
                    next_state = idle;
                    data_ready = 1'b1;
                end
                else 
                    tick_next = tick_reg+1;
            end
        end
    endcase
end

assign data_out = data_reg;
endmodule

   
   
	