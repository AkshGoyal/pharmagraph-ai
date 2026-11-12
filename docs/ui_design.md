# PharmaGraph interface design

The interface serves two people: a newcomer learning what the project does, and a reviewer investigating a batch. The opening overview explains the value before asking someone to interpret technical data. The live workspace retains the existing explicit-run, evidence and export workflow.

## Visual direction

A calm laboratory notebook with a navy navigation rail and an annotated evidence chart as the focal point. The design uses instrument-like clarity rather than pharmaceutical marketing imagery.

- Ink `#172D46`: headings and navigation.
- Teal `#087F82`: observed data and primary actions.
- Slate `#66758A`: secondary text and peer reference.
- Amber `#B56B16`: retained statistical intervals and attention.
- Canvas `#F3F6FA`: application background.
- Paper `#FFFFFF`: evidence and reading surfaces.

Typography uses the system sans-serif stack for legibility and offline operation. Display headings are moderately large and compact; explanatory text has a restrained line length. Left-aligned content, generous gutters and visible section boundaries distinguish explanations from evidence. Native Streamlit controls retain keyboard and assistive-technology behavior.

```text
Navigation rail | Page context and simulation status
                | Product explanation + open recorded example
                | Dataset scope, with definitions
                | Product / Business & use cases / Technical architecture
                | Annotated recorded chart | How to read the evidence
                | Select → compare → inspect → trace → export
```

The first draft could have looked like a generic operational dashboard with headline metrics. Instead, the centerpiece is a real six-observation temperature finding with a plain-English reading guide. Dataset counts are contextual facts, never success metrics. A recorded case is explicitly labeled and separated from live graph verification. No invented manufacturing records, causal conclusions, savings, accuracy figures or production-readiness claims are introduced.

## Information hierarchy

- **Project overview:** the problem, intended users, actual capability and technical architecture. Works without Neo4j.
- **Investigate a batch:** live data checks, four explained process channels, explicit investigation, findings, coverage, evidence, actual graph provenance and unchanged JSON.
- **Recorded walkthrough:** checked-in results for batches 031, 001 and 091; interactive point selection and source coordinates. Never presented as a fresh or live-verified result.
- **Data & glossary:** searchable plain-English vocabulary, cohort and source-unit explanations, dataset attribution.

Business users get a concrete review scenario and proposed measures of usefulness, explicitly distinguished from measured business outcomes. Technical users get responsibilities, data flow, detector arithmetic and the two-store consistency trade-off.
