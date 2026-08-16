# Product thesis — the judge that writes your law

Distilled 2026-08-16 from the product fight. Strategy notes, not build spec:
`implementation-plan.md` owns sequencing, `domain-model.md` owns behavior. When
this doc and a shipped decision disagree, the shipped decision wins until we
change it there.

**One-liner:** generators make infinite candidates; we make the judge — and the
judge writes down the law of your org as it rules.

---

## 1. The shift we ride

**"Exploration is now cheap and wide."** Human-made variants were expensive, so
every incumbent review tool models versions as a line (Frame.io stacks,
Filestage, Ziflow). AI inverted the cost: the bottleneck moved from *making*
variants to *tracking what was explored and why it lost*. A line cannot answer
"what did we explore and why did this one win." We model the tree.

**Kanban is not the opponent.** Kanban loses lineage instantly (true), but
buyers compare us to Frame.io's version stack, not Trello. Win the stack fight:
stacks are correct for narrow work; trees win when exploration goes wide — and
wide is the new normal.

## 2. Depreciating vs appreciating fears

**The deformed hand is a depreciating fear.** Artifact detection bets against
model improvement; value erodes on someone else's release schedule. Build on
fears that **grow** with generation quality:

| Fear | Who feels it | Why it appreciates |
| --- | --- | --- |
| **Truth** — "shipping a lie" | commerce teams using AI product imagery (image shows 5 buttons, SKU has 4 → returns, delisting, FTC) | born from genAI itself; unserved |
| **Law** | pharma/finance/alcohol marketing (MLR review, fines) | audit trail legally mandated; provenance = compliance artifact |
| **Consistency / drift** | game & entertainment art teams, franchise networks | more producers + more generation = more drift |
| **Accountability / provenance** | everyone | "prove a human approved this AI output" — AI-disclosure rules, C2PA |
| **Money** | agencies (margin per revision round), performance teams (spend) | volume scales cost of bad ships |

Reframe: not "we catch what's wrong with the image" but **"nothing ships that
is false, illegal, off-system, or unaccounted for — and here's the tree that
proves it."**

## 3. The pattern (what generalizes)

Every target user has: a **policy** (brand book / MLR rules / SKU truth / style
bible / locale norms), a **firehose of candidates**, and — load-bearing — an
**incomplete policy**: the written guideline is ~40% of the real rules; the rest
is tacit, revealed one dispute at a time.

> The scarce thing is not detection (commoditizing). It is the **org-specific
> rulebook that never got written down**. The product is an agent loop that
> compiles tacit judgment into an explicit, versioned, self-correcting rulebook
> by adjudicating real work.

**Common-law model:** guidelines = statute · each verdict = a case · each human
override = appellate ruling · memory rules = precedent · the tree = case
archive · human = court of appeal · agent = trial court · jurisdiction
transfers as precedent accumulates.

### The adjudication loop

POLICY → MEASURE → JUDGE → ESCALATE → ABSORB → PROVE → (rewrites POLICY)

Disciplines that make it real:

1. **Rules are first-class citizens** with asset-grade provenance: which dispute
   birthed it, who ratified, every hit, every override.
2. **No verdict without a citation.** A defect must name its rule. Can't cite
   one → it's a *proposed rule*, not a defect. Kills vibes-based false
   positives (the trust-killer).
3. **Rules self-prune on their record** — overridden 5 of last 6 citations =
   dying precedent, propose retirement.
4. **One health metric: override rate, trending down.** "Learns your taste,"
   measurable, per org per rule. The chart is the retention story and the moat
   — competitors can copy the checker, not eight weeks of your case law.

**Measure/judge split generalizes (decision 17):** every modality gets its ΔE —
image: ΔE2000/WCAG · video: LUFS, text reading-speed, platform safe-area,
first-frame · audio: LUFS, clipping, STT-vs-approved-copy. No verdict rests on
vibes in any modality.

## 4. The partner (second loop)

An adjudication loop is **reactive by construction** — judges speak when spoken
to. Initiative is a computation, not a personality: **desired state − current
state = gaps; act on the gap.** Prerequisite: a slot needs a **definition of
done** (spec: which deliverables, by when). Without a goal there is no gap and
no initiative — this is the rival-vs-deliverable question returning as spec.

### The agenda loop notices what a reactive agent cannot

- **Absence** — "no 9:16 yet, campaign exports Friday" (nothing was uploaded;
  no trigger exists)
- **Stall** — "variant 2 blocked on Maya's fix for 4 days"
- **Pickable moment** — recheck passes → owner pinged *at that instant*
- **Accumulating ambiguity** — "you overrode rule 7 three times, always on
  lifestyle shots — should the rule exclude them?" (agent initiates the
  clarifying question when its own case law turns contradictory)
- **Prediction from precedent** — pre-flag at upload; slot briefs from what
  previously won

**A verdict never arrives alone:** flag + proposed remedy (instruction,
generated fix candidate as branch, or named question). Critic vs partner.

### Anti-Clippy discipline

1. Every nudge **cites its gap** (same citation rule as defects).
2. **Autonomy ladder per action type:** observe → suggest → act-with-confirm →
   act-and-report. Rungs are *earned* by override rate. Mechanical crops climb;
   creative fixes stay at suggest; **approval never leaves the human.**
3. **Dismissed nudges are training data** — suppression feeds the same memory
   system. One learning mechanism, two loops.

Surface: agent keeps a ranked **agenda** per project ("what I'd do next") —
chief of staff, not chatbot. Sensors already exist (SSE feed, notifications,
needsAttention); missing: slot spec, gap detection, remedies-on-verdicts,
ladder.

## 5. Spine principle for expansion

**The tree is an airlock: no asset without a parent; nothing crosses
unreviewed.** Generation is allowed only as *response* — to a verdict or an
approved parent. Never a blank canvas (blank canvas = competing with
Canva/Adobe/Figma and voiding tool-agnostic neutrality). Every generated
output re-enters the tree as a node and gets judged like everything else.

## 6. Competitive map

Each category holds one of our three pieces; nobody joins them:

- **Review/approval seats** (Frame.io, Filestage, Ziflow, GoVisually,
  PageProof): workflow, linear versions, no verdicts, no lineage.
- **AI brand-compliance** (BrandGuard.ai, Frontify-moving-to-enforcement,
  CHILI GraFx/Storyteq): a gate, not a workspace — score in/verdict out, no
  loop, no memory.
- **Generation platforms** (Midjourney web, Krea, Leonardo, Freepik,
  Flora/Weavy): where variants are born; no QA depth or approval semantics.
- **Perforce/Helix**: has the tree topology (Revision Graph) but as an artifact
  of infrastructure, readable only by its operators. We invert: tree first,
  zero vocabulary.
- **The real competitor: glue** — Drive + Slack + `final_v2_FINAL.png`. The
  fight is activation energy.

Hard-to-retrofit joint: **verdicts-per-node compounding into per-brand
memory** — requires tree + agent + human loop from day one.

Line for the deck: *"Frame.io tells you what changed. BrandGuard tells you
what's wrong. Nobody tells you what you explored, what the agent caught, and
what your brand learned from it."*

## 7. User-value ranking (deadline-blind, fear-mapped)

1. **Trust loop** — precision + one-click dismissal-that-remembers. If the
   agent cries wolf, day-3 users stop reading flags and it catches nothing.
2. **Platform checker + export** — "CTA behind TikTok UI" = concrete, public,
   recurring, payable. Most underrated item.
3. **Share-link approval** — external reviewer, no account, one button. Ends
   the PM's dispute-fear. Biggest hole in current plan.
4. **Video** — half of an e-commerce brand's real output; v0 = frame-sample
   through existing pipeline, timestamped defects.
5. **Drive watched folder** — designer's existing habit *is* the upload
   trigger (decision 15 preserved). Explicit folder choice — no surprise QA.
6. **Fix-as-branch, persona-split** — solo owner: auto-fix mechanical = gold;
   agency designer: AI silently "fixing" their work = insult. Mechanical
   auto-offered; creative as instructions first.
7. Tree polish (default folded) · Gemini Live · Veo export.

**Tree demoted from headline to receipt:** daily question is "what needs me
now?" (attention queue); the tree answers "what happened?" (disputes,
onboarding, direction choice). Lead with "nothing ships wrong," show the tree
as proof. Sell outcomes, not topology.

**Approve from a phone:** the approval moment can't be desktop-only.

**Feedback translation:** "feels off" + pin → "CTA contrast 2.1:1, brand
minimum 3:1." Both personas' pain; measurements already stamped.

## 8. Gemini model map (organs, not integrations)

- **Gemini** — Scanner/Inspector, verdict engine (built)
- **Nano banana** — fix-as-branch: verdict → edit → child node → recheck
- **Veo** — derivation: approved static → motion variant → **re-enters tree,
  gets QA'd** (airlock applied to AI video)
- **Gemini Live** — voice at the interview moments the domain model already
  has (guideline grilling, rule collisions) + review copilot. Garnish, not
  organ: most users won't talk to software at a desk; the pain is "don't make
  me write a brand doc," already solved by extraction + collision-triggered
  questions.
- **Lyria** — only coherent if audio-as-modality exists; otherwise decoration.
  Audio is the weakest limb (rare buyer) — last or never, for demand reasons.

Bonus math ceiling: 0.6. Chosen trio: nano banana, Gemini Live, Veo. Caution:
0.6 bonus < one broken live demo; Live is websocket+mic+venue-wifi risk —
record the backup video the day it works.

## 9. Expansion wedges (ranked)

1. **AI product-fidelity QA for commerce** — best fear-per-effort. Closest to
   what's built (inspector vs SKU data/reference shots); fear created by the
   same trend that creates our users; cost measurable in returns. Reframes
   agent from "spots ugly" (depreciating) to "spots lies" (appreciating).
2. **Regulated review (MLR-style)** — deepest wedge: provenance legally
   required, review *is* the job. Enterprise sale, certification walls — the
   thing the fidelity beachhead grows into (same artifact: reviewed,
   versioned, remembering tree).
3. **Localization** — volume proof: 1 slot × 40 locale variants is the scene
   where every alternative UI collapses and the tree doesn't.

Pattern generalizes past creative (contracts, code-review norms, moderation
with house rules) — the loop never mentions pixels. We stay in creative;
the pattern is the company, not the vertical.

## 10. Open decisions

- **Slot spec / definition of done** — required for the agenda loop; also
  finally settles rival-vs-deliverable (a spec makes deliverables explicit).
- Default-folded tree opening (messy case: 30 nodes = 2548px wide unfolded).
- Provenance export (signed record / C2PA angle) — when.
- Persona split for fix-as-branch — where the mechanical/creative line sits.

## Keyword bank

exploration cheap and wide · the tree is an airlock · no asset without a
parent · nothing ships unreviewed · depreciating vs appreciating fears ·
shipping a lie · the rulebook that never got written down · common law:
statute/case/precedent · no verdict without a citation · rules are first-class
citizens · self-pruning precedent · override rate trending down · jurisdiction
transfer · adjudication loop vs agenda loop · initiative = desired state −
current state · definition of done · absence, stall, pickable moment,
accumulating ambiguity · a verdict never arrives alone · autonomy ladder ·
approval never leaves the human · dismissed nudges are training data · chief
of staff, not chatbot · tree as receipt, not headline · spots lies, not ugly ·
case law is the moat
