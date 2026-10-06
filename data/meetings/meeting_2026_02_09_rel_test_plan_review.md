FILE: meeting_2026_02_09_rel_test_plan_review.md
Meeting: Volta-7 Automotive Reliability Qualification Plan Review
Date: 2026-02-09 Time: 11:00 AM CST Location: Conference Room Pecan (Austin HQ)
Attendees: Kevin Tran (Reliability Engineer), Anna Becker (Quality Manager), Lisa Park (PE Manager)
Meeting Type: Reliability Review

Discussion
Lisa Park: Kevin, Anna, we are gearing up for NovaDrive's AEC-Q100 Grade 1 qualification. Kevin, present the reliability matrix and test hardware status.
Kevin Tran: The reliability qualification plan requires three distinct wafer lots for full qualification. We are pulling 77 units per lot for High Temperature Operating Life (HTOL), totaling 231 units.
Anna Becker: AEC-Q100 Grade 1 requires 1000 hours at 125°C ambient, correct?
Kevin Tran: Correct. Under accelerated voltage conditions—specifically 1.25 times nominal VDD, which equates to 1.15V on the 0.9V core, with junction temperature TJ held at 150°C.
Lisa Park: What about Temperature Cycling (TC) and Highly Accelerated Stress Test (HAST)?
Kevin Tran: TC is 1000 cycles from -55°C to +150°C, 77 units per lot. Unbiased HAST is 130°C and 85% relative humidity for 96 hours. All stress boards and thermal sockets have been calibrated in Lab C.
Anna Becker: Are intermediate readouts planned during HTOL?
Kevin Tran: Yes. We will pull the units at 168 hours, 500 hours, and final 1000 hours for ATE screening on Emma's test program across tri-temp: -40°C, 25°C, and 125°C.
Lisa Park: What silicon lot is loading into the HTOL chambers first?
Kevin Tran: We are loading 77 units each from Lots LOT-V7-002, LOT-V7-003 and LOT-V7-005, serialized U001 to U231 in that order. Chambers will be loaded and powered up by February 13.
Anna Becker: Make sure traveler sheets and calibration certificates for the HTOL oven temperature chambers are archived in the quality portal for the customer audit.
Kevin Tran: Traveler sheets are ready. I will monitor bias currents daily to ensure thermal runaway doesn't occur.

Decisions
1. Approved AEC-Q100 Grade 1 reliability test plan: HTOL (1000 hrs, 125°C, 1.25x VDD), TC (1000 cyc), and HAST (96 hrs).
2. Approved HTOL chamber load date of February 13, 2026, with intermediate readouts at 168h, 500h, and 1000h.

Action Items
Kevin Tran: Load 231 units into HTOL stress chambers and verify bias supply voltages — Due: 2026-02-13
Anna Becker: Review and archive chamber calibration certificates and qual travelers in QMS — Due: 2026-02-15
