# Competitive landscape and novelty assessment

Researched 2026-11-01 by three parallel web-research passes (commercial products, academic prior art, open-source and hackathon analogs). Every claim below carries a source. Caveats: most academic items were checked from abstracts, several are 2026 preprints without peer review, and two papers that could overlap most ([2607.21292](https://arxiv.org/abs/2607.21292), [2608.26780](https://arxiv.org/abs/2608.26780)) were not read in full. Forum threads (r/PLC, r/ControlTheory, Hacker News) were not reachable, so practitioner sentiment comes from vendor and academic sources.

Praxion's loop, numbered for reference:

1. Agent designs bounded experiments on an unknown plant and keeps a hypothesis ledger.
2. Agent writes controller source code from that evidence.
3. Code is sandboxed and scored by an independent evaluator on hidden scenarios before deployment.
4. Deployed under a trusted supervisor with hard limits.
5. Trusted monitor detects degradation after a hidden plant change.
6. Agent runs new experiments on the changed plant, re-identifies it, names a diagnosis.
7. Agent rewrites the controller; promoted only if it beats the frozen old version on the same seeds. Hash-stamped evidence bundle per run.

## Headline

No commercial product, paper, or public project was found that runs steps 1 to 7 end to end. Every step exists somewhere. The combination, and two specific pieces inside it, do not appear anywhere we could find:

- **Step 6 as experiments.** After a fault, every LLM system found diagnoses from data it is handed. None designs new experiments on the changed plant before rewriting.
- **Step 7 as a protocol.** No system promotes a repair only after a same-seed comparison against the frozen old version, with the author blind to the plant. The closest is a rollback-to-last-good in a hobby PID tuner.

Confidence from the three passes: about 75% that no shipping product does the full loop, about 85% that none rewrites controller code as the repair, about 85% that no public demo covers the loop end to end. The residual is stealth startups, closed vendor demos, and papers without code.

## Commercial players

Two product families exist and do not connect.

**LLM coding copilots** write PLC code from a human specification. None experiments on the machine, scores on hidden scenarios, or repairs after the machine changes.

| Product | Confirmed capability | Steps | Source |
|---|---|---|---|
| Siemens Industrial Copilot | SCL generation in TIA Portal; agent orchestrator announced 2025 | 2 | [automation.com](https://www.automation.com/article/siemens-ai-agents-industrial-automation) |
| Rockwell FactoryTalk Design Studio Copilot | Ladder logic generation and troubleshooting on Azure OpenAI; docs warn output may be inaccurate | 2 | [Rockwell docs](https://www.rockwellautomation.com/en-dk/docs/factorytalk-design-studio/current/contents-ditamap/getting-started/factorytalk-design-studio-copilot.html) |
| Schneider Industrial Copilot | Code generation with "tests against trusted libraries"; 30 to 50% savings self-reported | 2, weak 3 | [Automation World](https://www.automationworld.com/process/digital-transformation/article/55305398/schneider-electric-inside-the-new-industrial-copilot-with-schneider-electrics-aurelien-lesant) |
| Beckhoff TwinCAT CoAgent | Writes and refactors function blocks, generates unit tests | 2, weak 3 | [Beckhoff](https://www.beckhoff.com/en-us/company/press/twincat-chat-using-innovative-chatbot-technology-in-twincat-engineering-2023-04.html) |
| CODESYS | MCP server so outside LLMs can create function blocks | 2 | [CODESYS](https://www.codesys.com/products/engineering/ai-supported-engineering/) |
| Copia Automation Copilot | Ladder and structured text generation on a Git platform | 2 | [ABI Research](https://www.abiresearch.com/market-research/insight/7785221-copia-automation-announces-the-launch-of-i) |
| ABB Spec2Control (research) | Natural language to graphical control logic | 2 | [arXiv 2510.04519](https://arxiv.org/abs/2510.04519v1) |

**Closed-loop optimizers and adaptive controllers** identify and re-identify plant models and act on the loop. Their output is learned weights, model coefficients, or retuned gains inside structures humans wrote. None writes readable controller code.

| Product | Confirmed capability | Steps | Source |
|---|---|---|---|
| AspenTech DMC3 Adaptive | Automatic background step tests within limits; model-quality analysis flags degraded submodels, re-tests and re-identifies online | 1, 4, 5, 6 as coefficients | [AspenTech](https://www.aspentech.com/ja/products/pages/aspen-dmc3), [US 8,560,092](https://patents.google.com/patent/US8560092) |
| Emerson DeltaV InSight + Adapt | Loop monitoring with tuning recommendations; closed-loop PID retune on trigger events | 5, 6 as gains | [Adapt datasheet](https://emerson.com/documents/automation/product-data-sheet-deltav-adapt-continuous-closed-loop-adaptive-control-deltav-en-56194.pdf) |
| Yokogawa FKDPP | Reinforcement-learning control, 35-day autonomous run at JSR 2022, Aramco Fadhili 2025, under the DCS safety layer | 1 by trials, 4 | [BusinessWire](https://www.businesswire.com/news/home/20251028792329/en) |
| Imubit Optimizing Brain | Offline-RL controller writing setpoints to the DCS within limits; 90+ applications claimed; about $50M raised | 1 from history, 4, partial 5 and 6 | [GlobeNewswire](https://www.globenewswire.com/news-release/2024/09/19/2948742/0/en/Imubit-Launches-Optimizing-Brain-Solution-The-Process-Industry-s-First-Closed-Loop-AI-Optimization-Solution-Powered-by-Reinforcement-Learning.html) |
| Phaidra Alfred | RL agent for data-centre cooling; $50M+ Series B 2025 | 4, partial 5 and 6 | [GeekWire](https://www.geekwire.com/2025/phaidra-raises-50m-to-help-ai-data-centers-run-smarter-not-just-harder-by-boosting-energy-efficiency/) |
| Honeywell Forge APC | AI model building from history, online stepper and modeller | 1, 5, 6 as models | [Control Global](https://www.controlglobal.com/show-coverage/honeywell-users-group/article/55383228/ai-reduces-time-to-value-in-advanced-process-control) |
| Control Station PlantESP | Plant-wide loop forensics; diagnoses and advises | 5, partial 6 | [Processing](https://digital.processingmagazine.com/articles/accessible-loop-tuning-forensics) |

Predictive-maintenance vendors (Augury, Tractian) alert and open work orders; they do not act on the control loop ([Augury](https://www.augury.com/media-center/press/augury-maintainx-partner/)). Microsoft Project Bonsai (2020) was the clearest past attempt at simulation-trained industrial autonomy and appears discontinued ([VentureBeat](https://venturebeat.com/ai/microsoft-launches-project-bonsai-an-ai-development-platform-for-industrial-systems)). Composabl raised a $4.25M seed in 2024 for LLM-defined "skills" controlling equipment; no evidence the LLM writes code ([press release](https://markets.financialcontent.com/ms.intelvalue/article/zexprwire-2024-5-7-composabl-launches-breakthrough-no-code-ui-platform-for-industrial-strength-autonomous-agents-and-raises-425m)).

Five closest commercial analogs, ranked: AspenTech DMC3 Adaptive, Emerson InSight + Adapt, Yokogawa FKDPP, Imubit, the vendor copilots (tied).

## Academic prior art

The one lab that has published most of the pieces separately is Mehmet Mercangöz's group at Imperial College London, including LLM agents on the TCLab heater. Cite and contrast them explicitly.

**LLMs writing or designing controllers (crowded).** ControlAgent, UIUC 2024: multi-agent controller design with a Python compute agent and a 500-task benchmark, LTI models given not identified ([2410.19811](https://arxiv.org/abs/2410.19811)). AI Control Scientist, 2026: agents for modeling, code-writing and tuning ([2608.26780](https://arxiv.org/abs/2608.26780)). Luna Rueda, Mercangöz et al., 2026: LLM writes plant interface, controllers, scenarios and evaluation code, validates in closed loop, regenerates failing pieces, then Bayesian tuning ([2607.21292](https://arxiv.org/abs/2607.21292)). AgenticControl, 2025: agents design their own test scenarios ([2506.19160](https://arxiv.org/abs/2506.19160)). GenControl ([2506.12554](https://arxiv.org/abs/2506.12554)). LLM4PLC and Agents4PLC: PLC code with compiler and model-checker loops, success 47% to 72% ([2410.14209](https://arxiv.org/abs/2410.14209)). Code as Policies ([2209.07753](https://arxiv.org/abs/2209.07753)), Eureka ([2310.12931](https://arxiv.org/abs/2310.12931)), FunSearch with an independent evaluator ([Nature 2023](https://www.nature.com/articles/s41586-023-06924-6)).

**LLM agents on TCLab (exists, but not code authoring).** Vyas and Mercangöz 2025: the LLM outputs heater power directly with a validator and reprompt loop, roughly matching PID ([2507.07115](https://arxiv.org/abs/2507.07115), [2411.05904](https://arxiv.org/abs/2411.05904)). No TCLab project with an LLM writing the controller was found, including in APMonitor course material.

**LLM experiment design and identification (active, not on actuated plants under input limits).** SciExplorer 2025 ([2509.24978](https://arxiv.org/abs/2509.24978)), LLM-IDEA 2026 with an identifiability check ([2610.11253](https://arxiv.org/abs/2610.11253)), DiscoverPhysics ([2605.26087](https://arxiv.org/abs/2605.26087)), ASIA ([2605.10480](https://arxiv.org/abs/2605.10480)), LLM-SR ([2404.18400](https://arxiv.org/abs/2404.18400)). Roll-to-roll manufacturing framework 2025: a system-identification agent using classical RLS and subspace methods feeds controller design and a safety filter, with periodic refinement ([2511.22975](https://arxiv.org/abs/2511.22975)).

**Fault handling and self-repair (diagnosis exists, code rewrite is sparse).** From Detection to Action, Mercangöz group 2026: after detection, LLM agents propose recovery state machines and setpoint changes, checked against interlocks and a digital twin, with an engineered fallback. Actions, not controller code ([2606.28011](https://arxiv.org/abs/2606.28011), tutorial [2606.31635](https://arxiv.org/abs/2606.31635)). Act–Observe–Rewrite 2026: rewrites the whole Python controller between trials; a secondary summary reports a sandbox and fallback; no identification or monitor ([2603.04466](https://arxiv.org/abs/2603.04466)). INPROVF ([2503.13660](https://arxiv.org/abs/2503.13660)), RoboRepair ([2410.18893](https://arxiv.org/abs/2410.18893)), MAPE-K with LLMs ([2307.06187](https://arxiv.org/abs/2307.06187)).

**Safety (well-trodden; Praxion's supervisor is Simplex).** Sha 2001 ([Simplex](https://doi.org/10.1109/MS.2001.936213)), Black-Box Simplex ([2102.12981](https://arxiv.org/abs/2102.12981)), SOTER ([1808.07921](https://arxiv.org/abs/1808.07921)). A 2026 survey recommends exactly our shape, a fast certified safety filter under an LLM supervisor ([2602.03433](https://arxiv.org/abs/2602.03433)).

**Classical lineage a control professor will cite.** Self-tuning regulators, Åström and Wittenmark 1973: identify online, then redesign ([doi](https://doi.org/10.1016/0005-1098(73)90073-3)). Relay auto-tuning, Åström and Hägglund 1984: an automatic bounded experiment that yields PID gains ([doi](https://doi.org/10.1016/0005-1098(84)90014-1)). Fault detection, isolation and fault-tolerant control, Blanke et al. ([Springer](https://link.springer.com/book/10.1007/978-3-662-47943-8)). These cover steps 1, 2, 5, 6 and 7 in parameter form, with stability proofs Praxion lacks. They do not write open-ended code, keep natural-language hypotheses, gate on hidden seeds, or produce evidence bundles.

## Open-source and hackathon analogs

Only two runnable projects were found. llm-pid-tuner: a CLI that reads loop data over serial or from a thermal simulator and has an LLM suggest gains, with rollback to the last stable gains and a step-response identification script; 350 to 700 stars depending on source ([sourcepulse](https://www.sourcepulse.org/projects/26670850)). LSU agentic servo PID on Quanser hardware, monitor agent plus gain-updater agent ([LSU](https://repository.lsu.edu/bio_engineering_pubs/569)). DrEureka writes reward code tested against perturbed physics ([GitHub](https://github.com/eureka-research/DrEureka)). One AI Tinkerers LA hackathon entry retunes PID gains when a pendulum falls and retries, with no gating ([entry](https://la.aitinkerers.org/hackathons/h_KFAHphHUwmQ/entries/ht_xiYbvGxF1CI)). Nothing on Devpost, no Meta or Llama hackathon entry in this space. A LUT thesis found LLM PID tuning gives "variability between repeated tuning runs", which supports our distribution-not-anecdote rule ([LUT](https://lutpub.lut.fi/handle/10024/171307)).

## Step-by-step: how explored

| Step | Status | Who |
|---|---|---|
| 1 Bounded experiments, hypothesis ledger | Active, not on actuated plants under input limits | SciExplorer, LLM-IDEA, relay auto-tuning |
| 2 LLM writes controller code | Crowded | ControlAgent, AI Control Scientist, Agents4PLC, vendor copilots |
| 3 Sandbox + independent evaluator on hidden scenarios | Active for generated code, sparse for held-out plant scenarios | FunSearch, Agents4PLC, 2607.21292 |
| 4 Trusted supervisor with hard limits | Well-trodden | Simplex, every DCS vendor |
| 5 Monitor detects degradation | Classical and crowded | FDI, AspenTech, Emerson |
| 6 New experiments after fault, re-identify, diagnose in words | Sparse: diagnosis from given data exists, experiments after fault not found | 2606.28011, 2511.22975 |
| 7 Rewrite code, promote only on same-seed win vs frozen version | Essentially unexplored as a protocol | Act–Observe–Rewrite (between-trial rewrite, no gate) |

## What practitioners say the blocker is

The blocker is trust and auditability, not whether an LLM can write a controller. Schneider: "Real-time PLC systems demand predictable, auditable logic and cannot rely on probabilistic inference alone" ([SE blog](https://blog.se.com/digital-transformation/artificial-intelligence/2025/11/14/engineering-at-scale-how-ai-is-transforming-plc-coding/)). Industrial Shields: LLMs "hallucinate PLC registers, misinterpret industrial timing constraints, and suggest unsafe implementations"; treat the model as "an extremely fast junior engineer" ([Industrial Shields](https://www.industrialshields.com/blog/arduino-raspberry-pi-industrial-news-industry-4-0-iot-11/can-ai-really-program-plcs-what-llms-change-in-industrial-automation-and-what-they-don-t-718)). "Never use AI drafts in safety PLC logic without full IEC 61511 verification" ([instrumentationblog](https://www.instrumentationblog.in/chatgpt-for-plc-programming/)). This is the gap Praxion's independent gating, trusted supervisor and evidence bundle are built for.

## Honest verdict

- **Well-trodden:** an LLM writing a controller, LLM PID tuning, Simplex supervision, degradation monitoring, LLM agents on TCLab, identify-then-redesign adaptive control.
- **Recombination, not found anywhere as one system:** discovery, code authoring, hidden-seed gating, Simplex supervision, FDI-triggered redesign, in one auditable loop.
- **Genuinely new as far as three passes could find, medium confidence:** the agent designs new experiments after the fault before rewriting (step 6), and a same-seed promotion gate against the frozen version with a blindness test as the core protocol (step 7), plus a reproducible evidence bundle for every run.
- **Where the claim is weak:** on a first-order tank, a 1970s self-tuning regulator or relay auto-tune plus PID does the whole job with proofs. The novelty is the agent architecture and the evaluation protocol, not control performance. Say so.

## What a hostile reviewer will cite

Åström and Wittenmark 1973 ("solved 50 years ago, with proofs"); Blanke et al. ("FDI/FTC already detects, classifies and reconfigures"); the Mercangöz group ("LLM agents on TCLab and LLM fault-tolerant control with twin validation and fallback already exist"); Act–Observe–Rewrite ("LLMs rewriting controller code between trials with sandbox and fallback"); SciExplorer and LLM-IDEA ("LLMs choosing their own experiments"); Sha 2001 ("it's Simplex").

## Positioning implications

1. Lead with steps 6 and 7 and the evidence bundle, never with "an LLM writes a controller".
2. Cite the Mercangöz group and AspenTech DMC3 Adaptive as related work in the README, and state the difference in one sentence each: they adapt parameters or actions inside human-written structures; Praxion rewrites inspectable, diffable code and cannot game its own validation.
3. Add a relay auto-tune or self-tuning-regulator baseline as a fair re-tuning rival, scored on the same seeds. If it wins on the tank, that is the result; the value proposition then rests on diagnosis in words, evidence, and transfer to a second plant.
4. Keep the claim "no public end-to-end demonstration found as of 2026-11-01", with the caveats above, rather than "first ever".
