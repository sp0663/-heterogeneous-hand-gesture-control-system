module coord_assembler (
    input clk,
    input rst,
    input [7:0] fifo_data,
    input fifo_empty,
    output reg fifo_rd_en, 
    output reg [15:0] x_out,
    output reg [15:0] y_out,
    output reg [4:0] landmark_id,
    output reg valid_out
);

    reg [2:0] byte_counter; 
    reg [7:0] temp_id;
    reg [7:0] temp_x_high, temp_x_low;
    reg [7:0] temp_y_high, temp_y_low;
    reg assemble_flag;

    // FSM States to handle FIFO read latency
    localparam IDLE = 1'b0, WAIT_FIFO = 1'b1;
    reg state;

    always @(posedge clk) begin
        if (rst) begin
            byte_counter <= 0;
            assemble_flag <= 0;
            temp_id <= 8'h00;
            temp_x_high <= 8'h00;
            temp_x_low <= 8'h00;
            temp_y_high <= 8'h00;
            temp_y_low <= 8'h00;
            valid_out <= 0;
            x_out <= 16'h0000;
            y_out <= 16'h0000;
            landmark_id <= 5'h00;
            fifo_rd_en <= 0;
            state <= IDLE;
        end else begin
            valid_out <= 0;
            fifo_rd_en <= 0; // Default: do not read

            // Output assembled landmark data
            if (assemble_flag) begin
                x_out <= {temp_x_high, temp_x_low};
                y_out <= {temp_y_high, temp_y_low};
                landmark_id <= temp_id[4:0];
                valid_out <= 1;
                assemble_flag <= 0;
            end
            else begin
                case(state)
                    IDLE: begin
                        if (!fifo_empty) begin
                            // Capture the valid byte
                            case(byte_counter)
                                3'd0: temp_id <= fifo_data;
                                3'd1: temp_x_high <= fifo_data;
                                3'd2: temp_x_low <= fifo_data;
                                3'd3: temp_y_high <= fifo_data;
                                3'd4: temp_y_low <= fifo_data;
                            endcase

                            fifo_rd_en <= 1; // Assert pop request
                            state <= WAIT_FIFO; // Move to wait state

                            // Trigger assembly if 5 bytes collected
                            if (byte_counter == 3'd4) begin
                                assemble_flag <= 1;
                                byte_counter <= 0;
                            end else begin
                                byte_counter <= byte_counter + 1;
                            end
                        end
                    end
                    WAIT_FIFO: begin
                        // Wait 1 cycle for the FIFO read pointer & empty flag to update 
                        state <= IDLE;
                    end
                endcase
            end
        end
    end
endmodule