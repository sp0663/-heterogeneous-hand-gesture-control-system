
##  Nexys 4 DDR - Gesture Recognition System
##  100 MHz input, 50 MHz via Clocking Wizard MMCM



## Clock - 100 MHz onboard oscillator (E3)

set_property -dict { PACKAGE_PIN E3   IOSTANDARD LVCMOS33 } [get_ports clk_100MHz]


## Reset - BTNU (T18)

set_property -dict { PACKAGE_PIN T18  IOSTANDARD LVCMOS33 } [get_ports rst]


## USB-UART - PMOD JA
##   JA1 (B13) = rx  - connect PMOD TX here
##   JA2 (F14) = tx  - connect PMOD RX here
##   bottom row GND/VCC for power

set_property -dict { PACKAGE_PIN C4  IOSTANDARD LVCMOS33 } [get_ports rx]
set_property -dict { PACKAGE_PIN D4  IOSTANDARD LVCMOS33 } [get_ports tx]


## LEDs
##   LED15    : frame toggle   - toggles each complete frame
##   LED14    : UART RX active - on while bytes arriving
##   LED13    : assemble valid - on while landmarks assembling
##   LED12    : gesture valid  - on after classification fires
##   LED[7:5] : gesture_id     - 0=PINCH 1=FIST 2=OPEN 3=INDEX 4=UNKNOWN
##   LED[4:0] : landmark ID    - last assembled landmark (0-20)

set_property -dict { PACKAGE_PIN H17  IOSTANDARD LVCMOS33 } [get_ports {led[0]}]
set_property -dict { PACKAGE_PIN K15  IOSTANDARD LVCMOS33 } [get_ports {led[1]}]
set_property -dict { PACKAGE_PIN J13  IOSTANDARD LVCMOS33 } [get_ports {led[2]}]
set_property -dict { PACKAGE_PIN N14  IOSTANDARD LVCMOS33 } [get_ports {led[3]}]
set_property -dict { PACKAGE_PIN R18  IOSTANDARD LVCMOS33 } [get_ports {led[4]}]
set_property -dict { PACKAGE_PIN V17  IOSTANDARD LVCMOS33 } [get_ports {led[5]}]
set_property -dict { PACKAGE_PIN U17  IOSTANDARD LVCMOS33 } [get_ports {led[6]}]
set_property -dict { PACKAGE_PIN U16  IOSTANDARD LVCMOS33 } [get_ports {led[7]}]
set_property -dict { PACKAGE_PIN V16  IOSTANDARD LVCMOS33 } [get_ports {led[8]}]
set_property -dict { PACKAGE_PIN T15  IOSTANDARD LVCMOS33 } [get_ports {led[9]}]
set_property -dict { PACKAGE_PIN U14  IOSTANDARD LVCMOS33 } [get_ports {led[10]}]
set_property -dict { PACKAGE_PIN T16  IOSTANDARD LVCMOS33 } [get_ports {led[11]}]
set_property -dict { PACKAGE_PIN V15  IOSTANDARD LVCMOS33 } [get_ports {led[12]}]
set_property -dict { PACKAGE_PIN V14  IOSTANDARD LVCMOS33 } [get_ports {led[13]}]
set_property -dict { PACKAGE_PIN V12  IOSTANDARD LVCMOS33 } [get_ports {led[14]}]
set_property -dict { PACKAGE_PIN V11  IOSTANDARD LVCMOS33 } [get_ports {led[15]}]

## Bitstream / configuration

set_property CFGBVS         VCCO [current_design]
set_property CONFIG_VOLTAGE  3.3  [current_design]
