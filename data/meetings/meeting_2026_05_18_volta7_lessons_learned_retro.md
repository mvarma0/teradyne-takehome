FILE: meeting_2026_05_18_volta7_lessons_learned_retro.md
Meeting: Volta-7 Program Retrospective & Lessons Learned
Date: 2026-05-18 Time: 10:00 AM CST Location: Conference Room Pecan / Zoom
Attendees: Mike Chen (VP Product Engineering), Lisa Park (PE Manager), James Ortiz (Yield Engineer), Emma White (Test Engineer Lead), Kevin Tran (Reliability Engineer), Anna Becker (Quality Manager), Tom Harris (Field Application Engineer), Rosa Santos (Failure Analysis Engineer), Derek Cole (NPI Program Manager), Sara Nolan (Design Interface Engineer)
Meeting Type: Retro

Discussion
Mike Chen: We made the customer deadline, yield is at 82%, and NovaDrive is happy. But bottom line: we almost died in March. This retrospective is about radical candor. What broke, and how do we prevent it on Volta-8?
Lisa Park: Let's start with the elephant in the room: Rev A yield opening at 41% and the 500-hour HTOL failure.
Sara Nolan: I'll own the design side of the HTOL failure. The swap from the 280µm automotive clamp to the 120µm commercial clamp happened because layout was under intense schedule pressure and had routing congestion. We bypassed PE review on that waiver. That can never happen again.
Anna Becker: That's why the Design-to-PE Handoff Checklist is now mandatory in our QMS. No DRC waiver on IO or ESD cells can be signed off without PE reliability and quality approval.
James Ortiz: On the fab side, we waited until wafer sort to discover that Penang's CMP polish recipe was dishing Metal 3. We need inline defect metrology and optical inspection at M3 polish, not just end-of-line electrical test.
Emma White: And on test readiness—I shouldn't have to write ATE test programs from scratch without completed register documentation. We lost three weeks in January trying to decode the CAN-FD trim sequences.
Kevin Tran: The positive takeaway is how quickly Rosa and the FA team pinpointed the root cause. 72 hours from failure to FIB cross-section allowed us to tape out Rev B four weeks earlier than normal. And Rev B HTOL passed 600 hours this morning, still with zero fails.
Rosa Santos: Having the FIB and emission microscopy tools calibrated and on standby was critical.
Derek Cole: From program management: our NPI checklist was too linear. In Volta-8, we will run test pattern simulation and reliability socket prep concurrently with mask tooling.
Tom Harris: Customer-wise, our transparency in delivering the 8D report saved us. NovaDrive appreciated that we admitted the flaw and showed the physical data rather than making excuses.
Mike Chen: Well summarized. We grew as an organization through this fire. Lisa, take these lessons and bake them directly into our division SOPs.

Decisions
1. Instituted permanent policy requiring VP/PE sign-off on all design rule waivers for automotive BCD products.
2. Mandated inline fab optical inspection gates at Penang CMP metal layers for future product ramps.
3. Updated Product Engineering Division SOP-PE-042 to reflect lessons learned from Volta-7 ramp.

Action Items
Lisa Park: Update PE Division SOP-PE-042 with enhanced design handoff and reliability qual protocols — Due: 2026-05-25
Sara Nolan: Implement automated automotive ESD DRC rule decks across CAD tool flows — Due: 2026-05-28
