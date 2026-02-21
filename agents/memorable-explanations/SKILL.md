---
name: memorable-explanations
description: Use to intuitively, memorably explain abstract, complex, unfamiliar concepts. NOT for code generation, data retrieval, or when user just needs execution.
---

# Cognitive Anchoring

Your brain evolved for a physical, social world — not abstractions. Every good explanation
translates back into that format. Here are 8 translators, in two groups of four:

> **Face, Place, Tale, Scale.** → Structure (who, where, what happened, compared to what)
> **Touch, Feel, Chunk, Beat.** → Landing (tangible, emotional, holdable, sticky)

## The 8 Anchors

1. **Face — Cast characters, especially "you"**. We simulate other minds automatically. Cast abstract forces as agents with goals: "The load balancer is a bouncer deciding which server gets the next request." Archetypes beat real names — less baggage, more projection. The strongest move is self-reference: "Imagine _you_ are the packet" beats any third-person framing (Rogers et al., 1977).
2. **Place — Turn concepts into maps**. You're reading _down_ this list and the top already feels more important. That's spatial wiring. Convert structures into positions: above/below, inside/outside, near/far. The memory palace works because spatial recall is extraordinarily durable.
3. **Tale — Sequence creates cause for free**. Present two events in order and the reader infers the first _caused_ the second. "Because" makes anything more believable, even circularly (Langer). Explain processes as journeys. **Trap:** A good story _feels_ like understanding even when the causal model is wrong.
4. **Scale — Give comparisons, not absolutes**. "Two feet tall" lands instantly. "60 cm" makes you pause and convert. That pause is the cost of abstraction. The brain compares, it doesn't measure (Weber's Law). Always provide a reference object.
5. **Touch — Make abstractions graspable**. We "grasp" ideas because we literally learned by grasping. Use concrete, manipulable nouns. Software works because it's touchable: files, folders, windows, trash. **Critical:** Start concrete, then fade the scaffolding. Students who stay anchored to the metaphor can't generalize. The anchor is a bridge, not a destination.
6. **Feel — One sharp emotion beats ten clear arguments**. Forget these principles and your audience forgets _you_. (That sting is loss framing.) Fear, surprise, and reward tag memories for keeping. But high arousal _narrows_ cognition — use surgically, one vivid moment per explanation.
7. **Chunk — Respect the ~4 limit**. Eight items here already exceeds working memory (~4 chunks, Cowan 2001). That's why each anchor is one bolded word: a handle to grab. Organize material into ≤4 groups before explaining. Chunk first, explain second.
8. **Beat — Rhythm does the remembering**. Face, Place, Tale, Scale. Touch, Feel, Chunk, Beat. Say them aloud — the rhythm is already working. Rhyme, alliteration, parallel structure, and meter reduce cognitive load. That's why jingles outlast lectures.

## Applying the Anchors

1. **Audit:** What makes the concept hard? Invisible → Touch. Large-scale → Scale. Causally complex → Tale. Structurally dense → Chunk.
2. **Pick 2–4** whose structure mirrors the concept. Not every explanation needs all eight.
3. **Stack, don't scatter.** "Imagine _you're_ standing inside a database index" is Face + Place + Touch in one sentence.
4. **Flag where the anchor lies.** Every anchor is also a bias. "The electron _wants_ ground state — though electrons don't have desires; it's energy minimization."
5. **Plan the fade.** Start concrete, then gradually introduce the formal abstraction. The goal is independence from the metaphor.

## Quick Reference

| Anchor    | Mechanism                       | Watch out for                     |
| --------- | ------------------------------- | --------------------------------- |
| **Face**  | Theory of mind + self-reference | Anthropomorphizing non-agents     |
| **Place** | Spatial memory                  | Not all structures are spatial    |
| **Tale**  | Causal chain from sequence      | False causation from mere order   |
| **Scale** | Relative judgment               | Anchoring bias from first number  |
| **Touch** | Embodied cognition              | Concreteness as permanent crutch  |
| **Feel**  | Amygdala tagging                | Arousal narrows complex reasoning |
| **Chunk** | Working memory ~4               | Over-chunking hides connections   |
| **Beat**  | Rhythmic encoding               | Stickiness ≠ understanding        |

## Worked Example: DNS Resolution

**Without anchors:**
"DNS resolution translates domain names into IP addresses via hierarchical nameserver queries."

**With anchors:**

> Imagine **you** type "google.com." **[Face]** Your computer doesn't know where Google
> lives — it only knows a local guide, the resolver. **[Face: agent]**
>
> Think: asking for directions in an unfamiliar city. **[Place + Touch]** You ask a local,
> who asks the main information desk (root server), who says: ".com? Down that hall." The
> TLD server says: "Google? Here's their nameserver." Google's nameserver hands back
> 142.250.80.46 — the street address. **[Tale: journey, Place: directions]**
>
> Total time: ~50ms — faster than a blink. **[Scale]** If it breaks, you get the most
> frustrating error on the internet. **[Feel]**

Four characters, one journey, one emotional beat. **[Chunk + Beat]**
