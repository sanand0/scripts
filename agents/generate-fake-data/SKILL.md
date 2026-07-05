---
name: generate-fake-data
description: Use when creating REALISTIC synthetic data leading to actionable business hypotheses.
---

STEP 1. Research who the audience might be and their objective / key questions / pain points. Generate actionable hypotheses that'd make them go "Wow! We have this exact problem and never quantified it." Each must be:

- Counter-intuitive (NOT the first thing a domain expert would guess)
- Actionable (they could change something tomorrow)
- Slightly embarrassing (it implies a blind spot they should have caught)
- Expressible as a one-sentence headline: "We found that X, but only in Y"

These hypotheses should NOT be something that appears in a standard MBA case study or industry report. If a consultant could have guessed it without seeing the data, it's too obvious.
Build a 2-3 level hierarchical taxonomy of bottlenecks, edge-case customer behaviors, and silent failures listing the obscure, annoying realities and sample from these.
Then, pick hypotheses:

- 2 that are slightly surprising (confirming a suspicion)
- 2 that are genuinely counter-intuitive
- 1 that is uncomfortable (implies a process failure or oversight)

STEP 2. List columns that would be present in such data, briefly describing how the data might be distributed and inter-related. Before finalizing the schema, list 5 'tells' that would reveal this as synthetic to an expert in the domain. Then correct the code to avoid each one.

STEP 3. Write and run seed-randomized code to generate realistic fake data where these hypotheses are true in a statistically significant way. Remember - real data has:

- real names for people, places, products, etc. (not "Person 1", "Company A", etc.)
- extreme/unexpected distributions
- breaks in patterns
- surprising correlations
- standout entities (people, places, products, segments) that defy norms
- unusual, extreme, high-variance groups
- underutilization, phase transitions, tipping points, hidden populations, etc.

Use causal simulation where relevant, i.e. create entities (e.g., customers, machines) with hidden baseline traits and simulate entities interacting over time, with the data EMERGING from these interactions.

Select a small, realistic number of rows large enough to be convincing about realism and scalability - but not too unwieldy to generate or demo.
Over-sample rare but interesting segments to avoid losing the insight.

STEP 4. Act as a cynical, veteran data scientist and review the data. Does this look like real, messy enterprise data, or does it look mathematically generated? Point out any overly perfect distributions or obvious `random.choice()` artifacts, and rewrite the code to fix them.

STEP 5. Let the user download the output file(s) and the script to generate these, for reproducibility.
