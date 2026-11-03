# Presenter briefing: Praxion in plain words

For Mithran. This is the version of the project you carry in your head and say out loud. Nothing here requires control-theory background. Every number has a source in the repo; the sources are listed in Part 3 so you can check any of them. Read Parts 1 and 2 until you can say them without the page. Rehearse Part 4 out loud.

Written 2026-11-02; hardware answer (Q7) filled in 2026-11-03 after the TCLab runs.

---

## Part 1. The story

**One sentence.** Machines drift and engineers re-tune them by hand; Praxion is an AI that learns how a machine behaves, writes its own controller, rewrites it when the machine changes, cannot override its own safety layer, and proves every claim with evidence.

**Thirty seconds.** Every machine that holds something steady runs on a small piece of software called a controller. Writing it takes a human engineer who studies the machine first, and when the machine ages or breaks a little, the engineer has to come back and fix the software. Praxion does that engineer's job. It gets a machine it has never seen. It runs small, safe experiments to learn how it behaves. It writes the controller code itself. That code is tested on hidden situations before anyone trusts it. Then we secretly change the machine. A monitor notices things getting worse, the AI runs new experiments, works out what changed, and rewrites its own code. A separate safety layer it cannot touch has the final say on every command. Every run leaves an evidence bundle anyone can audit.

**Two minutes.** Use the demo script narration in `docs/DEMO_SCRIPT.md`. It is already written in these words and every spoken number is on screen in the same shot.

---

## Part 2. The mental model

You need six ideas. Each is one paragraph.

**1. A controller is a thermostat.** Your home thermostat measures the temperature, compares it to what you set, and turns the heat up or down. That is the whole job: measure, compare, act, repeat, many times a second. Our machine is a water tank. The controller measures the water level, compares it to the target (0.6 on a 0 to 1 scale), and sets the pump speed. The target is the *setpoint*. The acceptable margin around it is the *band* (0.55 to 0.65). "In-band" means the level stayed inside that margin.

**2. PID is the eighty-year-old recipe.** Almost every controller in the world is a PID: three numbers that say how hard to push based on how far off you are, how long you have been off, and how fast things are changing. Choosing those three numbers is called *tuning*. A badly tuned controller oscillates or never reaches the target. A human engineer tunes by studying the machine. In our runs the AI does not have to use PID; it writes whatever code it wants. Most of its controllers are PID-like with extras.

**3. Machines change, and then the tuning is wrong.** A pump wears, a valve sticks, a sensor slows, a leak opens. The controller that was perfect yesterday now overshoots or drifts. In industry this is a standing cost: someone has to notice, diagnose, and re-tune. We inflict these changes deliberately. The one most of our scored runs use is a *delay*: the pump starts responding about twenty seconds late. Others are a weaker pump, an extra leak, and a shifted drain.

**4. The AI is blind, and that is the point.** The model never sees the machine's equations, the hidden parameters, the true water level, or what we changed. It sees only what a real engineer would: noisy sensor readings, its own commands, and its own notes. A test suite (`tests/test_agent_blindness.py`) scans every piece of text the model ever receives and fails the build if anything secret leaks. Without this, nothing we claim would mean anything.

**5. Hidden scenarios are exam questions the student never sees.** Before the AI's controller is trusted, it is scored on ten situations it has never seen (different starting levels, different noise). After the change, the repair is scored on five more. These are called *hidden seeds*. The AI's own experiments use different ones. Scoring uses *MAE*, the average distance from the target; lower is better. The scoring rules were frozen before any scored run and have not been changed since.

**6. Trusted code has the last word.** The AI's code runs in a locked box (a Docker sandbox: no network, read-only, no privileges). A separate *supervisor*, written by us, sits between the AI's code and the pump. If the AI asks for something unsafe, the supervisor overrides it and logs that. If the level reaches the hard cutoff, the pump goes to zero no matter what. Those overrides count against the AI's score. The three *gates* are the promotion rules: G1, did it do real experiments and write valid code; G2, did the code pass eight of ten hidden scenarios with no safety violations; G3, did the repair cut post-change error by at least twenty percent on at least three of five hidden scenarios with no violations.

### Glossary

| Repo word | Plain words |
|---|---|
| plant | the machine |
| controller | the software holding the machine steady |
| PID | the standard three-number controller recipe |
| setpoint / target | the value we want (0.6) |
| band / in-band | the acceptable margin (0.55 to 0.65) and the share of time spent inside it |
| MAE | average distance from the target; lower is better |
| disturbance | the hidden change we inflict |
| actuator_lag | the pump starts responding late (about 20 s) |
| pump_derate / extra_leak / drain_shift | weaker pump / new leak / drain moved |
| supervisor, hard cutoff, override | the trusted safety layer, its emergency stop, and the times it stepped in |
| hidden seeds (1000s, 2000s) | exam scenarios the AI never sees |
| G1 / G2 / G3 | the three promotion gates |
| v1 / v2 | the controller before and after the repair |
| hypothesis ledger | the AI's running notes about what it believes and how sure it is |
| relay auto-tune | the classical textbook self-tuning method we race against |
| evidence bundle | the folder of hashed files from which anyone can rebuild a run |
| TCLab | the $50 heater kit, our real-hardware plant |

---

## Part 3. Numbers you may quote

Quote these and nothing else. Each has a file behind it.

| Claim | Number | Source |
|---|---|---|
| Live runs recorded (tank) | 13 scored runs on 5 different machines, plus 8 thermal runs | `docs/BENCHMARKS.md`, `artifacts/runs/` |
| Final protocol (v1.3), 5 machines | discovery 5/5, first controller passed 5/5, repair passed 5/5, diagnosis correct 5/5, original-machine performance kept 3/5 | `docs/IMPLEMENTATION_STATUS.md`, protocol v1.3 batch |
| Repair effect, v1.3 | post-change error cut 50% to 91% | `docs/BENCHMARKS.md` |
| Best run (the demo) | 90.6% cut, 5/5 scenarios, zero violations, delay measured at about 24 s by the AI (true about 20 s) | run `v13-s11-20261031-020922-a0e68e` |
| First full run | repair failed, recorded as FAIL, original controller kept | run `spark2-20261031-004636-3d012e` |
| Cost and time per run | median about $1.72 and about 13 minutes | `docs/BENCHMARKS.md` cross-run summary |
| Model | `muse-spark-1.3`; Wonder tried once | `model_calls.jsonl` in each bundle |
| Tests | 563 passing | `uv run pytest -q` |
| Hostile code corpus | 18 of 18 malicious controllers contained by the sandbox | `docs/IMPLEMENTATION_STATUS.md` |
| Classical rival (relay auto-tune) | lower post-change error in 11 of 12 runs (median 0.0121 vs 0.0376), using about 5× the plant time (368 s vs 74 s) and touching the hard cutoff on 2 of 5 machines | `docs/BENCHMARKS.md` head-to-head |
| Second-disturbance diagnostic | relay re-tune regains the band in 0 of 45 episodes on two families; Praxion repairs recover in about half and have lower error in 78 of 135; 3 of 9 repairs trip the supervisor | `artifacts/benchmarks/second_disturbance_diagnostic.md` |
| Thermal simulator, fan disturbance | repair cut error 97%, diagnosis correct | run `tclabsim-fan5-20261101-104237-bfe4bb` |
| Real hardware | two runs on a $50 TCLab heater kit: run 1 failed the performance gate (every experiment hit a 180 s cap; cap raised to 480 s); run 2 completed: controller passed first time, fan detected 66 s after it was switched on, diagnosis correct, repair cut error 85% (7.5 °C → 1.1 °C) on 10 of 10 scenarios | `artifacts/runs/hw1-20261102-234915-81765d`, `artifacts/runs/hw2-20261103-074537-698ba8` |

---

## Part 4. Twelve judge questions, answered in your voice

Each answer is about thirty seconds. Say them in your own words once you know them.

**Q1. What does it actually do?**
"It replaces the engineer who tunes a machine's controller and comes back to fix it when the machine changes. The AI gets a machine it has never seen, runs safe experiments, writes the controller code itself, gets scored on hidden tests, and then, when we secretly change the machine, it notices, investigates, diagnoses, and rewrites its own code. A safety layer it cannot touch has the final say."

**Q2. Isn't this just auto-tuning a PID? That has existed for decades.**
"Auto-tuners adjust three numbers inside a controller a human wrote. Praxion writes the whole controller as code, from experiments it designed itself, and when the machine changes it does not re-tune, it re-investigates and rewrites. We know the difference matters because we built the classic auto-tuner into our own evaluator and raced it. It won the headline metric on a single change, and froze solid the moment a second thing changed. That result is in our README."

**Q3. How do I know the model is not seeing the answers?**
"Three ways. The model only ever receives text built by one function, and a test scans every piece of that text for anything secret: parameters, the true level, the scenario numbers. The scored scenarios use seeds the model never sees; it does see their measured traces after a failed attempt, and we say so in the limitations. And every run leaves a bundle where the controller file is byte-identical to what the model returned, with hashes, so anyone can audit it. Our audit script does exactly that on screen in the video."

**Q4. The AI writes code that runs a machine. What if it writes something dangerous?**
"Two layers. The code runs in a locked box with no network, no file access and no privileges; we threw eighteen deliberately malicious controllers at it and all eighteen were contained. And the code never touches the pump directly. Our supervisor sits in between, overrides anything unsafe, and cuts power at a hard limit. Every override is logged and counted against the AI."

**Q5. Did it beat PID?**
"On the unchanged machine, no. A well-tuned PID is excellent at holding a level, and we say so. Praxion's value is what happens after the machine changes, when the hand-tuned PID is now wrong and nobody is there to fix it. On that, the repairs cut error between fifty and ninety-one percent on five different machines."

**Q6. Your own table says the classical method beat you. Why should I care?**
"Because we published it. We built the classical rival into our evaluator, scored it on exactly the same hidden scenarios, and it had lower error in eleven of twelve runs. It also used five times more time on the machine and touched the emergency cutoff on two machines, where our bounded experiments never did. Then we asked what it does when something else changes afterwards. It never recovers. Our repairs recover about half the time. Those are the real numbers and we would rather you see them from us."

**Q7. Does it work on real hardware?**
"Yes, once, on a fifty-dollar heater kit, and the first attempt failed. In the failed run the agent was only allowed three-minute experiments on a machine that takes about that long to settle, so it never saw a steady state and all five controllers it wrote were rejected by our gate. We raised the experiment limit, nothing else, and ran again. That run went end to end: it learned the board in thirty minutes, its first controller passed, we switched a fan on, the monitor caught it in sixty-six seconds, it ran four more experiments, named the cause correctly, and its repair cut the error by eighty-five percent on the changed machine. One run is a demonstration, not a distribution, and the repair comparison was scored on a model fitted to the changed board, not by running both controllers on it. All of that is in the README."

**Q8. Who pays for this? What is the business?**
"Anyone who runs machines that drift and does not have a control engineer on call: small factories, water utilities, building systems, labs. Today the fix is a visit from a specialist. The nearest commercial systems, like AspenTech's and Emerson's, re-identify models inside structures humans wrote and cost what refineries pay. Imubit and Phaidra have each raised about fifty million dollars for AI that acts on industrial control loops within safety limits. The market exists. Our wedge is the piece nobody does: the AI investigates the changed machine and rewrites readable code, under a supervisor, with evidence."

**Q9. What is new here? Siemens and Rockwell have copilots.**
"Their copilots write control code from a human's specification. They never touch the machine. The adaptive systems on the other side touch the machine but only adjust coefficients. We found no product, paper or demo that runs the whole loop: experiment, write code, score on hidden tests, deploy, detect the change, experiment again, rewrite, promote only if better. Two steps in particular appear nowhere we could find: designing new experiments on the changed machine before repairing, and promoting the repair only after a same-scenario comparison against the frozen old version."

**Q10. What failed? What are the limits?**
"Plenty, and it is all written down. Our first full run failed to repair and we kept the result. In two of the five final runs the repair fixed the changed machine but lost some performance on the unchanged one; the gate reports that rather than hiding it. Three of nine repairs that passed our gate turned out fragile on harsher scenarios, which told us five hidden scenarios are too few; raising that number is the first change for the next version. Our final protocol was tuned on the same five machines it was then measured on, so the five-for-five is in-sample. One plant type in simulation, one on hardware. We do not claim it works on any machine or that it is safe in general."

**Q11. Why Meta's Muse models? What did the model contribute?**
"Everything that required judgment. Muse designed every experiment and said which uncertainty it targeted and why it was safe. It kept the hypothesis ledger. It wrote every line of every controller; our code never patched one. After the change it chose the new experiments, named the diagnosis, and wrote the repair. Spark did all the scored runs at about a dollar seventy each. We used structured JSON output for every stage, which both Muse models handled."

**Q12. What is next?**
"Three things, in order. More hidden scenarios per gate, because five overstated robustness. More runs on the heater kit until we have a distribution, not an anecdote. Then a second plant type, to test whether the protocol transfers. Not a bigger product, a deeper one."

---

## Part 5. What never to say

From the demo script rules, plus three traps.

- Never: "works on any machine", "guaranteed safe", "beats PID", "deployed in production", "Muse learned physics".
- Never quote a number that is not in Part 3.
- Trap 1: being asked about the relay result and sounding defensive. Lead with "we built it and published it", then the cost it paid, then the second-disturbance result.
- Trap 2: being asked a deep control-theory question (stability margins, Nyquist, observer design). Answer: "I am not a control engineer. The protocol was designed so the controller's quality is judged by the frozen evaluator, not by me. The gains and diffs are in the bundle and I am happy to pull them up." Then stop. Honest beats fluent.
- Trap 3: overselling the hardware run. It is one run, the first attempt failed, and the repair comparison is twin-scored. Say all three before anyone asks.

---

## Part 6. Rehearsal

1. Read Parts 1 and 2 twice. Close the page. Say the thirty-second version to a wall. Repeat until it comes out in your words.
2. Have someone fire Q1 to Q12 in random order. Thirty seconds each. If an answer runs past forty-five seconds, it has a sentence too many.
3. Watch the demo video with the sound off and narrate it live from `docs/DEMO_SCRIPT.md`. Twice.
4. Say Q7 out loud until the failed first run comes out as naturally as the successful second one.
