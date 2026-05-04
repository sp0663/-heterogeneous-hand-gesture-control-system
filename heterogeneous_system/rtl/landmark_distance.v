// Computes the squared Euclidean distance between two landmarks using their x and y coordinates.

module landmark_distance (
    input [15:0] x1,
    input [15:0] y1,
    input [15:0] x2,
    input [15:0] y2,
    output [32:0] dist_sq           // squared distance between landmarks
);
    wire signed [16:0] dx, dy;
    assign dx = $signed({1'b0, x2}) - $signed({1'b0, x1});
    assign dy = $signed({1'b0, y2}) - $signed({1'b0, y1});
    
    assign dist_sq = dx*dx + dy*dy;
    
endmodule