"""Explanatory views over checked-in evidence; no live-data or scoring fallback."""
import json
from html import escape
from pathlib import Path

import streamlit as st

from . import demo

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ("Project overview", "Investigate a batch", "Recorded walkthrough", "Data & glossary")
CHANNELS = {
    "aeration_rate": ("Air flow", "Air supplied to the fermenter. Source-reported flow in L/h."),
    "sugar_feed_rate": ("Sugar feed", "Sugar solution supplied to the fermenter. Source-reported flow in L/h."),
    "ph": ("Acidity (pH)", "The source's pH reading; the chart preserves the reported scale."),
    "temperature": ("Temperature", "Fermenter temperature in Kelvin (K), preserved from the source."),
}


def html(value):
    st.html(value)


def navigate(view):
    st.session_state["page_navigation"] = view


def setup():
    st.set_page_config(page_title="PharmaGraph | Batch evidence, explained", page_icon="🧪", layout="wide")
    st.html(f"<style>{(ROOT / 'assets/interface.css').read_text()}</style>")
    with st.sidebar:
        html('''<div class="brand"><span class="brand-mark" aria-hidden="true"></span><span class="brand-name">PharmaGraph</span></div>
          <p class="brand-description">Follow the evidence.</p>''')
        view = st.radio("Explore the platform", VIEWS, key="page_navigation")
        st.divider()
        st.caption("Penicillin fermentation\n\nIndPenSim dataset · Release V2")
        html('''<div class="rail-note"><strong>A research demonstration</strong>
            Explore published simulation data and the evidence behind a finding.
            Statistical findings support review; they do not establish a root cause or a product-quality decision.</div>''')
    return view


def page_context(section, recorded=False):
    label = "Recorded evidence" if recorded else "Published simulation data"
    html(f'<div class="page-context"><span>PharmaGraph <span aria-hidden="true"> / </span> <strong>{escape(section)}</strong></span>'
         f'<span class="pill {"recorded" if recorded else ""}">{label}</span></div>')


def recorded_result(batch="031"):
    if batch not in ("031", "001", "091"):
        raise ValueError("Unknown recorded example")
    return json.loads((ROOT / f"docs/evidence/investigation/batch{batch}.json").read_text())


def chart(finding, compact=False):
    points = [{**point, "status": "scored"} for point in finding["evidence"]]
    figure = demo.finding_figure(finding, points, unit_reported=finding["reference"]["unit_reported"])
    for trace in figure.data:
        if trace.name == "Observed":
            trace.update(line={"color": "#087f82", "width": 3}, mode="lines+markers", marker={"size": 6},
                         hovertemplate="%{x:.1f} h<br>Observed: %{y:.3f} K<extra></extra>")
        elif trace.name == "Peer median":
            trace.update(line={"color": "#75869f", "width": 2, "dash": "dash"})
    # This recorded view contains exactly six retained observations, not a full-batch trajectory.
    figure.update_layout(height=290 if compact else 360, showlegend=False,
                         font={"family": "Arial, sans-serif", "size": 11, "color": "#617187"},
                         margin={"l": 15, "r": 18, "t": 15, "b": 35},
                         xaxis_title="Hours since this batch began", yaxis_title="Temperature (K)",
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    figure.update_xaxes(range=[85.97, 87.03], dtick=.2, gridcolor="#edf1f5", zeroline=False)
    figure.update_yaxes(gridcolor="#edf1f5", zeroline=False)
    figure.update_shapes(opacity=.08)
    return figure


def chart_key():
    html('''<div class="chart-key"><span><i class="swatch"></i>Observed temperature</span>
      <span><i class="swatch peer"></i>Peer median</span>
      <span><i class="swatch envelope"></i>Statistical reference envelope</span></div>''')


def explanations(items):
    html('<div>' + ''.join(f'<div class="explanation"><span class="marker">{i}</span><div><strong>{escape(title)}</strong>'
         f'<p>{escape(body)}</p></div></div>' for i, (title, body) in enumerate(items, 1)) + '</div>')


def workflow():
    steps = [
        ("Choose a batch", "Start with one simulated fermentation run."),
        ("Compare with peers", "Use the same control group and elapsed time."),
        ("Inspect a finding", "Look for persistent statistical differences."),
        ("Trace the source", "Check readings, file, row and column."),
        ("Export evidence", "Download the complete investigation as JSON."),
    ]
    html('<div class="workflow">' + ''.join(f'<div class="workflow-step"><span class="step-index">Step {i}</span>'
         f'<strong>{title}</strong><p>{body}</p></div>' for i, (title, body) in enumerate(steps, 1)) + '</div>')


def footer():
    html('<div class="footer">PharmaGraph · Local research MVP · Data: Stephen Goldrick (2019), IndPenSim, Mendeley Data V2. '
         '<a href="https://doi.org/10.17632/pdnjz7zz5x.2" target="_blank" rel="noopener noreferrer">Dataset & attribution</a> · '
         '<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a>. '
         'Selected fields are normalized; statistical comparisons are derived.</div>')


def overview():
    page_context("Project overview")
    left, right = st.columns([3.1, 1], gap="large")
    with left:
        html('''<div class="hero"><h1>Understand the batch.<br>Follow the evidence.</h1>
          <p>A workspace for turning unusual fermentation measurements into an inspectable investigation.
          See what changed, how it compares, and exactly where the evidence comes from.</p></div>''')
        st.caption("Here, a batch is one computer-simulated run of a penicillin-producing fermentation process.")
        actions = st.columns(2)
        actions[0].button("Explore the recorded example", type="primary", on_click=navigate,
                          args=("Recorded walkthrough",), width="stretch")
        actions[1].button("Investigate a batch", on_click=navigate, args=("Investigate a batch",), width="stretch")
    with right:
        html('''<div class="hero-aside"><strong>Start with a real question</strong>
          “Which part of this batch differs from comparable batches, and can I show the original measurements?”
          <br><br>Built for process-data review and learning.</div>''')
    html('''<div class="scope"><div><strong>100 batches</strong><span>Simulated fermentation runs</span></div>
      <div><strong>113,935 samples</strong><span>Each row holds multiple channels</span></div>
      <div><strong>4 assessed channels</strong><span>Air flow, sugar feed, pH, temperature</span></div>
      <div><strong>Every 12 minutes</strong><span>Comparison at matching time ticks</span></div></div>''')
    product, business, technical = st.tabs(["The product", "Business & use cases", "Technical architecture"])
    with product:
        st.markdown("### One finding, explained")
        html('<p class="section-intro">Follow a recorded result from a temperature difference to its original source. '
             'These six observations come from the checked-in Batch 031 investigation.</p>')
        left, right = st.columns([1.85, 1], gap="large")
        result = recorded_result()
        finding = result["findings"][0]
        with left, st.container(border=True):
            html('<div class="section-header"><div class="case-heading"><strong>Batch 031 · Temperature</strong>'
                 '<span>Above peer reference</span></div><span class="pill recorded">Recorded</span></div>')
            st.caption("Retained interval: 86–87 h · 6 observations · 29 eligible peers")
            chart_key()
            st.plotly_chart(chart(finding, compact=True), width="stretch", key="overview_recorded_chart", config={"displayModeBar": False})
            st.caption("Only the retained interval is shown. The envelope is a statistical reference, not an operating specification or confidence interval.")
        with right:
            explanations([
                ("What changed?", "At 86 h, temperature was 298.38 K. The median of 29 available peer readings was 297.99 K: a difference of 0.39 K."),
                ("Why was it retained?", "The statistical difference persisted for six consecutive readings. The rule requires at least five in the same direction."),
                ("Where is the evidence?", "The first reading traces to CSV data row 34,755, column index 17 (the 18th column), Temperature(T:K)."),
            ])
        st.markdown("### An investigation you can follow")
        workflow()
        html('<div class="note"><strong>What this result means:</strong> the batch differs persistently from its peer reference. '
             'A reviewer still needs process context to establish a cause or assess product quality.</div>')
    with business:
        business_view()
    with technical:
        technical_view()
    footer()


def business_view():
    st.markdown("### Less evidence gathering. More informed review.")
    st.write("When a process trend looks unusual, a reviewer needs to assemble the batch history, choose a fair comparison and locate the original readings. PharmaGraph brings those steps into one traceable workflow.")
    a, b = st.columns(2, gap="large")
    with a, st.container(border=True):
        st.markdown("#### The intended user")
        st.write("A process engineer or manufacturing science reviewer investigating why a fermentation batch differs from comparable runs. A student or technical reviewer can use the same workflow to learn how evidence is assembled.")
        st.caption("The current implementation uses a published simulator, rather than manufacturing or patient records.")
    with b, st.container(border=True):
        st.markdown("#### The useful output")
        st.write("An inspectable case: the time interval, observed values, peer statistics, skipped comparisons and exact source coordinates, together in a reproducible JSON file.")
        st.caption("The intended benefit is easier evidence assembly. Time savings and business ROI have not been measured.")
    st.markdown("#### Three concrete use cases")
    st.dataframe([
        {"Use case": "Investigate a persistent difference", "Question": "When did temperature diverge from suitable peers?", "What the product supplies": "Ranked intervals, observed readings and peer support"},
        {"Use case": "Review supporting evidence", "Question": "Can I trace this number back to the published source?", "What the product supplies": "Batch / variable / artifact / source relationships and CSV coordinates"},
        {"Use case": "Check assessment coverage", "Question": "Was there enough compatible data to compare?", "What the product supplies": "Cohort exclusions, skipped ticks and explicit not-assessed states"},
    ], hide_index=True, width="stretch")
    st.markdown("#### A practical review scenario")
    explanations([
        ("A reviewer opens Batch 031", "They inspect four process channels and explicitly run the comparison. The detector retains the 86–87 h temperature interval."),
        ("They verify the comparison", "The reference is operator-controlled batches 032–060, excluding the target. Only finite readings at the same elapsed time contribute."),
        ("They take the evidence into further review", "They inspect six readings and their source coordinates, then export JSON. Recipe, equipment and quality records would be needed for a real investigation."),
    ])
    with st.expander("How could business usefulness be measured?"):
        st.write("A future pilot could measure time to assemble a source-backed case, source-lookup completion rate and reviewer understanding of findings versus unassessed results. Establish a baseline and agreed review tasks first. These are proposed measures, not reported project outcomes.")
    html('<div class="note"><strong>Current scope:</strong> a local portfolio MVP. It has no validated manufacturing workflow, '
         'authentication, multi-user case management or calibrated detection-accuracy claim.</div>')


def technical_view():
    st.markdown("### A connected index. A numerical evidence layer.")
    st.write("Python prepares and compares the data. Neo4j identifies the right records and their provenance. Parquet stores the measurements. Streamlit and Plotly make the result inspectable.")
    html('''<div class="architecture" aria-label="Data flow: verified source to Parquet and Neo4j, then Python comparison and UI">
      <div class="node"><strong>Published source</strong><p>IndPenSim V2 ZIP<br>Checksum and schema checks</p></div>
      <div class="connector" aria-hidden="true">→</div>
      <div class="store-pair"><div class="node primary"><strong>Parquet · measurements</strong><p>Batch, sample and variable tables</p></div>
      <div class="node"><strong>Neo4j · connected index</strong><p>Identities, definitions and source links</p></div></div>
      <div class="connector" aria-hidden="true">→</div>
      <div class="node"><strong>Python comparison</strong><p>Peer reference → intervals<br>Streamlit / Plotly → JSON export</p></div></div>''')
    st.caption("This diagram explains the system design. Live graph relationships are queried and verified separately in the investigation workspace.")
    st.markdown("#### How the comparison works")
    explanations([
        ("Choose comparable batches", "Use the same documented process-control group, exclude the target batch and align exact 0.2-hour ticks. At least 10 finite peers are needed at each tick."),
        ("Calculate a statistical distance", "Find the peer median and MAD (median absolute deviation). The score is |observed − peer median| ÷ (1.4826 × MAD). It is a ratio, not a probability or severity grade."),
        ("Retain persistent differences", "Keep a run only when scores are strictly above 6 for at least 5 consecutive observations in one direction. Five observations span 48 minutes between endpoints. Rank intervals by mean point score."),
        ("Preserve evidence and identity", "Keep measurements and source coordinates in the result. Recheck file hashes and graph-generation compatibility before reusing cached displays or results."),
    ])
    a, b = st.columns(2, gap="large")
    with a, st.container(border=True):
        st.markdown("#### Why two stores?")
        st.write("The graph is a small index of relationships: 239 nodes and 708 relationships in the recorded load. Full time series stay columnar in Parquet. The graph does not calculate scores or establish causality.")
        st.caption("SQL joins could support these same fixed relationships. Two stores add a consistency and operational cost.")
    with b, st.container(border=True):
        st.markdown("#### What happens with missing data?")
        st.write("Missing, unmatched or unscoreable ticks break a run. No interpolation, fill or extrapolation is applied. Zero peer spread with a different observed value is unscoreable; an equal value gets score zero.")
        st.caption("Published fault annotations and harvest outcomes are excluded from detector inputs.")
    with st.expander("Implementation map"):
        st.dataframe([
            {"Component": "scripts/ingest_indpensim.py", "Responsibility": "Verify source; normalize fields; publish Parquet and manifest"},
            {"Component": "scripts/graph.py + load_graph.py", "Responsibility": "Validate versions; load identities and structural relationships"},
            {"Component": "scripts/investigation.py", "Responsibility": "Select peers; score ticks; retain intervals and evidence"},
            {"Component": "scripts/demo.py", "Responsibility": "Live checks; plotting; provenance queries; canonical JSON"},
            {"Component": "app.py + scripts/interface.py", "Responsibility": "Investigation workspace and explanatory views"},
        ], hide_index=True, width="stretch")
    with st.expander("Does the project use an AI model?"):
        st.write("The implemented detector is deterministic statistics written in Python. There is no trained machine-learning model, LLM or chatbot in this MVP. Neo4j stores identities and relationships; it does not infer causes. The reproducible peer comparison and traceable evidence are the implemented capabilities.")


def walkthrough():
    page_context("Recorded walkthrough", recorded=True)
    st.title("Follow one case, end to end.")
    st.write("Explore checked-in investigation results without starting the local database. This view does not run the detector or verify the current graph.")
    batch = st.selectbox("Choose a recorded case", ["031", "001", "091"], key="recorded_batch",
                         format_func=lambda x: {"031": "Batch 031 · A persistent temperature difference", "001": "Batch 001 · Assessed, no retained intervals", "091": "Batch 091 · Not assessed"}[x])
    result = recorded_result(batch)
    state = demo.result_state(result)
    if not result["findings"]:
        if state["kind"] == "undocumented":
            st.warning(state["message"])
            st.markdown("### Why the system stops here")
            st.write("The process-control regime for batches 091–100 is undocumented. Without a justified comparison group, the detector does not assess this batch. It does not invent peers or treat missing assessment as a clean result.")
        else:
            st.info(state["message"])
            st.markdown("### What a no-interval result means")
            st.write("The detector assessed the batch, but no interval met all persistence and score rules. This does not establish that the process was normal, safe or within a product specification.")
        st.caption(f"Assessed channels: {state['assessed_variable_count']} of 4 · Skipped or unscoreable variable/tick comparisons: {state['skipped_tick_count']:,}")
    else:
        finding = result["findings"][0]
        metrics = st.columns(4)
        metrics[0].metric("Retained interval", "86–87 h", help="Hours since this simulated batch began.")
        metrics[1].metric("Supporting observations", "6", help="Consecutive 12-minute readings. Six observations span one hour between endpoints.")
        metrics[2].metric("Eligible peer batches", str(len(result["reference_cohort"]["members"])), help="Same documented control regime; Batch 031 excluded. Finite-peer support can vary by time tick.")
        metrics[3].metric("Mean deviation score", f"{finding['statistical_deviation_score']:.4f}", help="Mean of point scores in this interval. Not a probability, severity or quality grade.")
        with st.container(border=True):
            st.markdown("### Temperature compared with peers")
            chart_key()
            st.plotly_chart(chart(finding), width="stretch", key="walkthrough_chart", config={"displaylogo": False})
            st.caption("Six recorded interval observations only. Shading = peer median ± 6 × reference spread; not an operating specification or confidence interval.")
        st.markdown("### Inspect a measurement")
        point_index = st.select_slider("Observation time (hours since batch start)", options=list(range(len(finding["evidence"]))),
                                       format_func=lambda i: f"{finding['evidence'][i]['time_h']:.1f} h", key="recorded_point")
        point = finding["evidence"][point_index]
        left, right = st.columns([1, 1], gap="large")
        with left, st.container(border=True):
            st.markdown(f"#### At {point['time_h']:g} hours")
            st.dataframe([
                {"Measurement": "Observed temperature", "Value": f"{point['observed_value']:.3f} K", "Represents": "Published simulation measurement"},
                {"Measurement": "Peer median", "Value": f"{point['reference_median']:.3f} K", "Represents": f"Middle value of {point['peer_count']} finite peers"},
                {"Measurement": "Difference", "Value": f"{point['observed_value'] - point['reference_median']:.3f} K", "Represents": "Observed minus peer median"},
                {"Measurement": "Point deviation score", "Value": f"{point['deviation_score']:.4f}", "Represents": "Absolute difference ÷ scaled peer MAD"},
            ], hide_index=True, width="stretch")
            st.caption("Small peer spread can produce a large score for a small absolute difference. Review both the units and the score.")
        with right, st.container(border=True):
            st.markdown("#### Trace to the original source")
            ref = finding["reference"]
            html(f'<div class="source-path"><strong>Batch {batch} → Temperature → Source CSV</strong><br>'
                 f'{escape(ref["source_member_path"])}<br>Data row <strong>{point["source_row_number"]:,}</strong> (excluding header)<br>'
                 f'Column index <strong>{ref["source_column_index"]}</strong> (zero-based; column {ref["source_column_index"] + 1} when counting from one)<br>'
                 f'Exact header: <strong>{escape(ref["source_header"])}</strong></div>')
            st.caption("Coordinates are from the recorded result. Current graph provenance is only verified in the live workspace. ‘V3’ in the CSV name is distinct from the published V2 release.")
        with st.expander("All six evidence records, including source coordinates"):
            st.dataframe(demo.evidence_rows(finding), hide_index=True, width="stretch")
        st.warning(f"Partial coverage: {state['skipped_tick_count']:,} variable/tick comparisons were skipped or unscoreable across the full assessment. This interval does not imply complete batch coverage.")
    with st.expander("Recorded coverage by channel"):
        st.dataframe([{"Channel": CHANNELS[v["variable"]][0], "Status": v["status"], "Scoreable observations": v["scored_point_count"],
                       "Skipped comparisons": sum(v["skipped_tick_counts"].values()), "Retained intervals": v["retained_interval_count"]}
                      for v in result["variable_results"]], hide_index=True, width="stretch")
    st.download_button("Download recorded investigation JSON", data=demo.canonical_json_bytes(result),
                       file_name=f"recorded_batch_{batch}_investigation.json", mime="application/json", key="recorded_download", on_click="ignore")
    st.button("Open the live investigation workspace", on_click=navigate, args=("Investigate a batch",))
    footer()


GLOSSARY = {
    "Fermentation": "A biological production process. This dataset simulates penicillin fermentation; it is not a record of real manufacturing.",
    "Batch": "One complete simulated fermentation run, identified separately from every other run.",
    "Channel / variable": "A measured quantity. The detector assesses air flow, sugar feed, acidity (pH) and temperature.",
    "Elapsed time": "Hours since this particular batch began. Matching elapsed time does not guarantee matching biological phase.",
    "Tick": "One numbered 12-minute step. Tick 430 × 0.2 hours = 86 hours.",
    "Peer": "Another batch in the same documented control regime. The target batch is always excluded.",
    "Control regime": "How the process was controlled: recipe-driven, operator-controlled, or advanced process control (APC) with Raman measurements. The documented group is used as a coarse compatibility proxy.",
    "Median": "The middle value in sorted readings. For an even count, average the middle two.",
    "MAD": "Median absolute deviation: the median distance of peer readings from their median.",
    "Reference spread": "1.4826 × peer MAD. Used to scale the difference between the observed reading and the peer median.",
    "Deviation score": "Absolute difference from the peer median divided by reference spread. A statistical ratio, not a probability or severity grade.",
    "Retained interval": "A consecutive run of readings meeting the strict score and same-direction persistence rules.",
    "Reference envelope": "Peer median ± 6 reference spreads. A statistical comparison, not a confidence interval, specification or safe operating range.",
    "Provenance": "The identities, file fingerprints and source coordinates explaining where an evidence record came from.",
    "Neo4j graph": "A database of records and their source relationships. Different from a trend chart, and not a model of cause and effect.",
    "Parquet": "The columnar files containing prepared batches, measurements and variable definitions.",
    "Manifest / checksum": "A list of expected files and their digital fingerprints. Detects changed bytes; does not prove scientific correctness.",
    "JSON export": "Structured text preserving the investigation, its evidence and limitations. Same verified inputs and settings produce the same result.",
}


def glossary():
    page_context("Data & glossary")
    st.title("The data, in plain language.")
    st.write("A few definitions make the charts and comparisons much easier to read.")
    search = st.text_input("Find a term", placeholder="Try ‘peer’, ‘score’ or ‘provenance’", key="glossary_search")
    terms = [(term, definition) for term, definition in GLOSSARY.items() if search.casefold() in (term + " " + definition).casefold()]
    if terms:
        st.dataframe([{"Term": term, "What it means here": definition} for term, definition in terms], hide_index=True, width="stretch")
    else:
        st.info("No matching terms. Try a shorter search or clear the field to see all definitions.")
    st.markdown("### How comparison groups are chosen")
    st.dataframe([
        {"Batches": "001–030", "Documented control regime": "Recipe-driven", "Comparison": "Same group; target excluded"},
        {"Batches": "031–060", "Documented control regime": "Operator-controlled", "Comparison": "Same group; target excluded"},
        {"Batches": "061–090", "Documented control regime": "APC / Raman", "Comparison": "Same group; target excluded"},
        {"Batches": "091–100", "Documented control regime": "Undocumented", "Comparison": "Not assessed"},
    ], hide_index=True, width="stretch")
    st.caption("These groups are coarse compatibility proxies. Similar control regimes and elapsed times do not ensure equivalent recipes or biological phases.")
    st.markdown("### Source and units")
    st.write("Stephen Goldrick's IndPenSim Mendeley Data V2 release contains published computer-simulated penicillin fermentation records. The app preserves source scales and missing values. Temperature is reported in Kelvin, air and sugar-feed flow in L/h, and acidity using the source's pH label.")
    html('<div class="note"><strong>Reading the three outcomes:</strong> “Finding retained” means a persistent statistical difference. '
         '“No retained intervals” means the rule retained none, not proof of normal or safe operation. '
         '“Not assessed” means the evidence did not support a comparison.</div>')
    footer()
