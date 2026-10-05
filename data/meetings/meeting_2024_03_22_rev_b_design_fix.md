FILE: meeting_2024_03_22_rev_b_design_fix.md
Meeting: Volta-7 Rev B Silicon Mask Fix & Execution Strategy
Date: 2024-03-22 Time: 10:00 AM CST Location: Conference Room Bluebonnet (Austin HQ)
Attendees: Sara Nolan (Design Interface Engineer), Mike Chen (VP Product Engineering), James Ortiz (Yield Engineer), Emma White (Test Engineer Lead), Kevin Tran (Reliability Engineer)
Meeting Type: Cross-functional

Discussion
Mike Chen: We have one shot at Rev B. If Rev B fails qualification, FastChip is out of automotive power management. Sara, what is the design fix?
Sara Nolan: We removed the commercial 120µm clamp cell and inserted the fully certified AEC-Q100 280µm multi-finger ESD clamp macro (`ESD_CLAMP_HV_280`). To accommodate the 160µm width increase without expanding the die size, we restructured the adjacent dummy metal fill and shifted the IO routing pitch by 0.4 microns.
Kevin Tran: Did you simulate the holding voltage and trigger current under 150°C junction temperature conditions?
Sara Nolan: Yes. SPICE simulations show trigger voltage VT1 at 6.8V, holding voltage VH at 5.4V, and secondary breakdown current IT2 exceeding 4.2 Amperes. That gives us over 100% margin above the worst-case HTOL operating point.
Emma White: Does the IO layout change alter any pin capacitance or AC timing on the CAN-FD lines?
Sara Nolan: Parasitic extraction shows an increase of only 0.15 pF on Pin 14 and Pin 22. Emma, your test program limits won't need to change.
James Ortiz: What layers are changing in the mask shop?
Sara Nolan: Only four metal layers and the contact layer: Active, Contact, Metal 1, Via 1, and Metal 2. Layers M3 and above remain completely untouched.
Mike Chen: Bottom line: how many weeks from tape-out to silicon on the tester?
Sara Nolan: Mask tape-out is tomorrow, March 23. Penang fab has reserved five hot-lot slots on wafer stock held at Poly gate stage. That allows us to skip front-end fab cycles.
James Ortiz: Hot-lot processing through metal backend will take 20 days. ETA Austin sort is April 21.
Mike Chen: Approved. Pull the trigger on tape-out tomorrow morning.

Decisions
1. Approved Rev B design layout incorporating `ESD_CLAMP_HV_280` cell with 4-mask change (Active, Contact, M1, Via1, M2).
2. Fab authorized to inject 5 hot-lots (LOT-V7-020 through LOT-V7-024) utilizing pre-fabricated poly-stage base wafers.

Action Items
Sara Nolan: Complete DRC/LVS physical verification and release Rev B mask stream tape-out — Due: 2024-03-23
James Ortiz: Coordinate hot-lot expedition protocol with Penang fab operations — Due: 2024-03-25
