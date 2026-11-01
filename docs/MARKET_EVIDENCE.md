# Market evidence: what badly maintained control loops cost today

Collected 2026-11-01 for the Praxion demo. Each figure is labeled by source quality: **primary** (the study or vendor's own report), **secondary** (a reputable outlet quoting a study), or **vendor** (a company with a product to sell). Use primary and secondary figures on slides; mention vendor figures only with that label.

## 1. The size of the problem: most industrial control loops are not working well

| Claim | Figure | Quality | Source |
|---|---|---|---|
| Share of PID loops in a plant running in manual (operator switched the automation off) | about 30% | secondary (Van Overschee & De Moor review; Control Engineering) | [Control Engineering](https://www.controleng.com/is-automated-pid-tuning-dependable/) |
| Of loops left in automatic, share that would have less variance in manual | 65% | secondary | [Control Engineering](https://www.controleng.com/is-automated-pid-tuning-dependable/) |
| Loops in auto still on factory-default tuning | 25% | secondary | same |
| Loops oscillating because of valve stiction, i.e. the machine changed and the controller did not | 20 to 30% (30% in a Canadian paper-mill survey) | secondary (Yang & Clarke 1999; AIChE) | [AIChE 2009](https://aiche.org/conferences/aiche-spring-meeting-and-global-congress-on-process-safety/2009/proceeding/paper/37b-oscillatory-control-loops-lost-economic-benefits-can-anything-be-done) |
| Overall share of loops with a performance problem | 60% ("only about 40% satisfactory") | secondary (ISA CAP study guide summarizing surveys) | [ISA CAP guide](https://open-exam-prep.com/study-guides/isa-cap/operation-maintenance-optimization-moc-decommissioning/loop-auditing-control-optimization) |
| Share of regulatory controllers that are PID (so the problem is everywhere) | 97% of 11,000+ surveyed | primary (Desborough & Miller, Honeywell, CPC VI 2001) | [paper PDF](https://skoge.folk.ntnu.no/prost/proceedings/cpc6-jan2002/desborough.pdf) |

**Demo line:** "Around 97% of the regulators in industry are the same kind of loop you just watched. Surveys for twenty years have found that roughly 30% are switched off by operators, and most of the rest are tuned once and never again."

## 2. What the drift costs: downtime

| Claim | Figure | Quality | Source |
|---|---|---|---|
| Unplanned downtime, world's 500 largest companies | about $1.4 trillion per year, about 11% of revenue | primary (Siemens, True Cost of Downtime 2024) | [Siemens TCOD 2024 PDF](https://assets.new.siemens.com/siemens/assets/api/uuid:1b43afb5-2d07-47f7-9eb7-893fe7d0bc59/TCOD-2024_original.pdf) |
| Per large facility, 2021–22 edition | $129 million per year | primary (Siemens/Senseye 2022, 72 companies) | [Senseye 2022](https://www.senseye.io/blog/the-true-cost-of-downtime-2022), [Siemens 2022 PDF](https://assets.new.siemens.com/siemens/assets/api/uuid:3d606495-dbe0-43e4-80b1-d04e27ada920/dics-b10153-00-7600truecostofdowntime2022-144.pdf) |
| Hourly cost, FMCG | about $23,600 per hour | primary (same 2022 edition) | same |

Caveat: these figures cover all causes of downtime, not only control-loop drift. Praxion addresses the slice where equipment behavior changed and nobody re-tuned. No source isolates that slice; do not claim a share of the $1.4T.

## 3. What the drift costs: energy

| Claim | Figure | Quality | Source |
|---|---|---|---|
| Regular PID re-tuning, average energy reduction | 5 to 15%, plus 2 to 5% throughput | secondary (UK Energy Efficiency Best Practice Programme, quoted by Control Engineering) | [Control Engineering](https://www.controleng.com/pid-loop-control-tuning-advice/) |
| HVAC faults in US commercial buildings, energy wasted | 0.7 quads per year, nearly $14 billion | primary (US DOE Building Technologies Office, 2021) | [DOE 2021 PDF](https://www.energy.gov/sites/default/files/2021-09/bto-peer-2021-afdd-evaluation-fault-prevalence-comm.pdf) |
| Share of commercial HVAC and lighting energy wasted by faults | up to 20% | primary (TIAX for DOE, 2006; dated) | [FMLink summary](https://www.fmlink.com/tiax-report-analyzes-energy-savings-potential-in-us-commercial-buildings/) |
| Savings from fixing faults (commissioning, 1,500+ buildings) | median 6% whole-building | primary (LBNL) | [LBNL](https://eta-publications.lbl.gov/sites/default/files/empirical_analysis_of_the_prevalence_.pdf) |
| Savings reported by buildings using fault detection | median 9% | primary (DOE Smart Energy Analytics Campaign) | [DOE 2021 PDF](https://www.energy.gov/sites/default/files/2021-09/bto-peer-2021-afdd-evaluation-fault-prevalence-comm.pdf) |
| Fault prevalence dataset | 60,000+ HVAC units, 90+ fault types | primary (LBNL, Crowe et al. 2023) | [LBNL](https://eta-publications.lbl.gov/sites/default/files/empirical_analysis_of_the_prevalence_.pdf) |

**Demo line:** "The US Department of Energy estimates faulty building HVAC alone wastes about $14 billion of energy a year, and the buildings that detect and fix faults save a median 9%. The oven on this table is that loop in miniature."

## 4. The home side

| Claim | Figure | Quality | Source |
|---|---|---|---|
| US appliance repair industry revenue | $7.0 billion (2025) | primary (IBISWorld) | [IBISWorld](https://www.ibisworld.com/united-states/market-size/appliance-repair/1710) |
| US HVAC services market (install, service, repair) | about $152 billion, 125,000 firms, 570,000 technicians | secondary (IBISWorld 2024 via Orbital) | [Orbital](https://www.withorbital.com/data/hvac-industry-statistics/) |
| HVAC repair cost range | $100 to $6,200; compressor $750 to $2,000 | vendor (WebFX) | [WebFX](https://webfx.com/industries/home-repair/hvac/marketing-statistics) |
| Smart thermostat savings, conservative | about 8% of heating and cooling, about $50 per year | primary (EPA ENERGY STAR) | [ENERGY STAR FAQ](https://www.energystar.gov/products/heating_cooling/smart_thermostats/smart_thermostat_faq) |
| Smart thermostat savings, manufacturer | 10 to 12% heating, 10 to 15% cooling, $131 to $145 per year | vendor (Nest, ENERGY STAR certification testing) | [Builder](https://www.builderonline.com/?p=76763), [Google](https://store.google.com/magazine/nest-thermostat-savings/?hl=en-US) |

**Why this matters for Praxion:** a thermostat with better *scheduling* saves 8 to 15%. Praxion is about better *control of the device itself* after it drifts, a layer below the thermostat, which no consumer product addresses today.

## 5. Where people overpay now, and what Praxion changes

1. **Tuning is a human service call.** In industry a loop is tuned at commissioning by an integrator and re-tuned only when someone complains. Loop-tuning audits are sold as consulting engagements. Praxion makes re-tuning an automatic, audited event triggered by the machine's own drift.
2. **Operators switch automation off.** About 30% of loops in manual means a human is doing the controller's job by hand, badly, every shift. A controller that notices it is wrong and repairs itself is the alternative to switching it off.
3. **Energy burns silently.** Oscillating and sluggish loops waste 5 to 15% of energy in process plants and up to 20% in building HVAC. Nobody is paid to notice.
4. **Appliance vendors ship one tuning for every home.** Every heat pump, EV charger, and oven is tuned for a nominal unit, then installed into a different duct, wiring, and climate, and ages differently. Field adaptation is a support cost the vendor eats today.
5. **Old equipment has no vendor.** Kilns, lab ovens, and process units whose manufacturer is gone cannot be re-tuned because nobody has the model. Praxion builds the model from experiments.

## 6. What not to claim

- Do not attribute a share of the $1.4T downtime figure to control drift; no source isolates it.
- Do not present the 5 to 15% energy figure as measured by Praxion; it is the literature's figure for human re-tuning. Praxion's measured results are its own benchmark table.
- Do not use the "30% of HVAC energy is wasted" line; it comes from vendor blogs and is above what the primary studies support.
