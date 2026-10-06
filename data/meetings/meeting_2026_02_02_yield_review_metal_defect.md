FILE: meeting_2026_02_02_yield_review_metal_defect.md
Meeting: Yield Review & Failure Analysis Readout — Metal 3 CMP Defect
Date: 2026-02-02 Time: 03:00 PM CST Location: Conference Room Bluebonnet / Zoom
Attendees: James Ortiz (Yield Engineer), Lisa Park (PE Manager), Rosa Santos (Failure Analysis Engineer), Mike Chen (VP Product Engineering)
Meeting Type: Yield Review

Discussion
Mike Chen: It's February 2nd. Lot LOT-V7-004 finished sort. James, did the needle move?
James Ortiz: Yes. We are up to 54.8%—let's call it 55% packageable yield. An improvement from 41%, but still 15 points short of our target.
Lisa Park: Rosa, walk us through the deprocessing results from the Wafer 03 failure analysis.
Rosa Santos: We completed cross-sectional FIB and scanning electron microscopy (SEM) on the failing Bin 4 dies. The failure mode is inter-metal bridging between adjacent Metal 3 signal lines in the core execution pipeline.
Mike Chen: Bridging? Is it particle contamination or litho bridging?
Rosa Santos: Neither. It is chemical-mechanical planarization (CMP) dishing and erosion. In regions with dense metal patterns, the fab's CMP polishing process over-polished the inter-layer dielectric (ILD), causing copper puddling and micro-bridges across adjacent lines.
James Ortiz: That completely matches what I saw in the defect pareto log! Defect DEF-001 and DEF-003 show slurry residue and micro-scratches spiking on Metal 3.
Lisa Park: Has Penang fab acknowledged the CMP issue?
James Ortiz: I met with the Penang fab process integration team this morning. They confirmed their platen down-force was set at 2.8 psi on the Cu CMP tool, which is too aggressive for this pattern density.
Mike Chen: Bottom line: when does the fab adjust the recipe, and when do we see 70% yield?
James Ortiz: After our January 26 containment request they ran 2.1 psi as a split on Lot LOT-V7-004, which is why that lot jumped to 55%. Starting today they lock 2.1 psi on every lot and switch to the low-abrasive Slurry B-4, beginning with Lot LOT-V7-006. That lot should hit Austin sort by mid-February.
Lisa Park: Excellent work pinpointing this, Rosa. Let's make sure Penang fab locks the CMP process window with tight SPC limits.

Decisions
1. Identified Metal 3 CMP dishing/copper puddling as root cause for Bin 4 logic failures on Rev A silicon.
2. Penang fab instructed to lock CMP polish down-force at 2.1 psi (from 2.8 psi), move to Slurry B-4 and enforce revised SPC controls on all active lots.

Action Items
James Ortiz: Track the first full-recipe run on Lot LOT-V7-006 (2.1 psi + Slurry B-4) in the yield tracker — Due: 2026-02-06
Rosa Santos: Publish formal Failure Analysis Report on Metal 3 CMP bridge defects — Due: 2026-02-09
