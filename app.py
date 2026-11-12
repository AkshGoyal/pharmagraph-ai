"""Local Streamlit evidence demo over the existing graph and investigation engine."""
import os

import streamlit as st

from scripts import demo, graph, investigation, interface as ui


@st.cache_resource(show_spinner=False)
def _driver(connection_key):
    return graph.driver_from_env()


@st.cache_data(show_spinner=False)
def _bundle(processed_dir, content_key):
    return graph.validate_processed(processed_dir)


@st.cache_data(show_spinner=False)
def _trends(processed_dir, content_key, batch_id, connection_key, reference_key, database, _driver, _bundle):
    return demo.load_trends(_driver, _bundle, batch_id, database=database)


def _clear_current():
    for key in ("investigation_result", "investigation_key", "finding_selector", "plot_contexts"):
        st.session_state.pop(key, None)


def _method(result=None):
    with st.expander("Method, reference cohort and limitations"):
        st.write("At each observed elapsed-time tick, compare the published simulation value with the median of compatible peers. "
                 "Reference spread is 1.4826 × median absolute deviation (MAD).")
        st.write("Defaults: at least 10 finite peers per tick; deviation score strictly greater than 6; "
                 "at least 5 consecutive observations in the same direction. Five observations span 0.8 h between endpoints.")
        st.write("Intervals rank by mean point deviation score, then peak score, configured variable order and start tick. "
                 "The target batch is always excluded. Missing or unscoreable ticks break runs; no values are filled or extrapolated.")
        if result is not None:
            cohort = result["reference_cohort"]
            st.write(f"Eligible cohort: {len(cohort['members'])} batches · compatibility group: {cohort['compatibility_group']}")
            st.caption("Compatibility metadata is used only to select peers. It is not a detector feature.")
            if cohort["members"]:
                st.dataframe(cohort["members"], hide_index=True, width="stretch")
            st.write("Target exclusion", cohort["target_exclusion"])
            st.caption("Cohort exclusions")
            st.dataframe(cohort["exclusions"], hide_index=True, width="stretch")
        for limitation in result["limitations"] if result is not None else investigation.LIMITATIONS:
            st.write("• " + limitation)


def workspace():
    ui.page_context("Investigate a batch")
    st.title("Investigate a batch")
    st.write("Inspect the process, compare suitable peers, then follow a finding back to its source.")
    st.caption("Live workspace · The graph and processed-file identities are checked on every interaction. Analysis runs only when you choose Run investigation.")
    processed_dir = os.environ.get("PHARMAGRAPH_PROCESSED_DIR", str(graph.DEFAULT_OUTPUT))
    try:
        identity = demo.content_identity(processed_dir)
        connection_key = demo.connection_fingerprint()
        database = graph.environment().get("NEO4J_DATABASE", "neo4j")
        driver = _driver(connection_key)
        bundle = _bundle(identity["processed_dir"], identity["content_key"])
        # Live checks deliberately run outside all cached functions.
        batches = demo.live_context(driver, bundle, database)
        generation = identity["content_key"] + connection_key
        if st.session_state.get("data_generation") != generation:
            _clear_current()
            st.session_state["investigation_cache"] = {}
            st.session_state.pop("batch_selector", None)
            st.session_state["data_generation"] = generation
        by_id = {b["batch_id"]: b for b in batches}
        options = list(by_id)
        default_index = next((i for i, batch_id in enumerate(options) if by_id[batch_id]["batch_ref"] == 31), 0)
        with st.container(border=True):
            choose, context, action = st.columns([1, 1.5, 1], vertical_alignment="bottom", gap="large")
            with choose:
                batch_id = st.selectbox("Choose a batch", options=options, index=default_index,
                    format_func=lambda value: f"Batch {by_id[value]['batch_ref']:03d}", key="batch_selector",
                    help="One batch is one simulated fermentation run. Changing the batch clears the previous displayed result.")
            with context:
                ref = by_id[batch_id]["batch_ref"]
                regime = "Recipe-driven" if ref <= 30 else "Operator-controlled" if ref <= 60 else "APC / Raman" if ref <= 90 else "Undocumented"
                st.markdown(f"**{regime} control regime**")
                st.caption("Compared only with the same documented group; target excluded." if ref <= 90 else "Compatibility is undocumented. This batch cannot be assessed.")
            with action:
                run = st.button("Run investigation", type="primary", key="run_investigation", width="stretch")
        current_key = demo.result_cache_key(identity, batch_id, connection_key)
        if st.session_state.get("investigation_key") != current_key:
            _clear_current()
        references = demo.reference_inventory(driver, bundle, batch_id, database)
        reference_key = demo._hash(references)
        trends = _trends(identity["processed_dir"], identity["content_key"], batch_id,
                         connection_key, reference_key, database, driver, bundle)
        if trends["references"] != references:
            raise ValueError("Cached trend references differ from current graph")
        batch = trends["batch"]
        st.subheader("Process context")
        st.caption(f"{batch['sample_count']:,} stored observations · elapsed {batch['time_start_h']:g}–{batch['time_end_h']:g} h · "
                   "source-reported units; no conversion or imputation")
        for start in (0, 2):
            columns = st.columns(2, gap="medium")
            for column, variable in zip(columns, investigation.DEFAULT_VARIABLES[start:start + 2]):
                with column, st.container(border=True):
                    label, description = ui.CHANNELS[variable]
                    st.markdown(f"**{label}**")
                    ui.html(f'<p class="channel">{description}</p>')
                    figure = demo.trend_figure(trends["measurements"][variable], variable,
                                              references[variable]["unit_reported"])
                    figure.update_layout(title=None, margin={"l": 15, "r": 15, "t": 10, "b": 25})
                    st.plotly_chart(figure, width="stretch", key="trend_" + variable, config={"displaylogo": False})
        if run:
            cache = st.session_state.setdefault("investigation_cache", {})
            if current_key not in cache:
                with st.spinner("Comparing compatible peer measurements…"):
                    cache[current_key] = investigation.investigate_batch(driver, batch_id,
                        processed_dir=identity["processed_dir"], database=database)
            st.session_state["investigation_result"] = cache[current_key]
            st.session_state["investigation_key"] = current_key
            st.session_state.setdefault("plot_contexts", {})
        result = st.session_state.get("investigation_result")
        if result is None:
            st.info("Ready to compare. Choose Run investigation above to check these four channels against compatible peers. The trends shown here are observed measurements, without a peer comparison yet.")
            _method()
            return
        state = demo.result_state(result)
        st.subheader("Investigation results")
        st.caption("Derived analysis · Statistical comparisons calculated from the published simulation measurements.")
        if state["kind"] in ("undocumented", "unscorable"):
            st.warning(state["message"])
        else:
            st.info(state["message"])
        if state["skipped_tick_count"]:
            coverage_label = "Coverage is partial" if state["assessed_variable_count"] else "No scoreable reference comparisons"
            st.warning(f"{coverage_label}: {state['skipped_tick_count']:,} variable/tick assessments were skipped or unscoreable. "
                       "Review compatibility, finite-peer coverage and zero-MAD diagnostics below.")
        coverage = [{"variable": v["variable"], "status": v["status"], "skipped_reason": v["skipped_reason"],
                     "target_observations": v["target_point_count"], "scoreable_observations": v["scored_point_count"],
                     "retained_intervals": v["retained_interval_count"],
                     "skipped_ticks": sum(v["skipped_tick_counts"].values())} for v in result["variable_results"]]
        summary = st.columns(3)
        summary[0].metric("Retained intervals", len(result["findings"]), help="Persistent same-direction differences meeting all detector rules. Not a count of confirmed faults.")
        summary[1].metric("Assessed channels", f"{state['assessed_variable_count']} / 4", help="Channels with scoreable peer comparisons. See coverage below for skipped ticks.")
        summary[2].metric("Eligible peer batches", len(result["reference_cohort"]["members"]), help="Same documented control regime; target excluded. Available finite support can vary at each tick.")
        with st.expander("Assessment coverage by channel"):
            st.caption("A skipped tick is a comparison that could not be scored. A retained interval does not imply complete batch coverage.")
            st.dataframe(coverage, hide_index=True, width="stretch")
        with st.expander("Coverage and skipped-tick diagnostics"):
            for variable in result["variable_results"]:
                st.write(variable["variable"], variable["skipped_tick_counts"])
                if variable["skipped_ticks"]:
                    st.dataframe(variable["skipped_ticks"], hide_index=True, width="stretch")
        findings = result["findings"]
        if findings:
            st.markdown("### Retained findings")
            st.caption("Ranked by mean statistical deviation score. A larger ratio indicates a larger difference relative to peer spread, not greater product risk.")
            st.dataframe([{"rank": f["rank"], "variable": f["variable"], "direction": f["direction"],
                "start_time_h": f["start_time_h"], "end_time_h": f["end_time_h"],
                "start_tick": f["start_tick"], "end_tick": f["end_tick"], "observation_count": f["point_count"],
                "mean_statistical_deviation_score": f["statistical_deviation_score"]} for f in findings],
                hide_index=True, width="stretch")
            by_finding = {finding["finding_id"]: finding for finding in findings}
            finding_id = st.selectbox("Finding", options=list(by_finding), key="finding_selector",
                format_func=lambda value: f"{ui.CHANNELS[by_finding[value]['variable']][0]} · {by_finding[value]['start_time_h']:g}–"
                                         f"{by_finding[value]['end_time_h']:g} h · {by_finding[value]['direction']}")
            finding = by_finding[finding_id]
            plot_contexts = st.session_state.setdefault("plot_contexts", {})
            plot_key = current_key + ":" + finding["variable"]
            if plot_key not in plot_contexts:
                plot_contexts[plot_key] = demo.plotting_points(driver, bundle, result, finding, database)
            st.plotly_chart(demo.finding_figure(finding, plot_contexts[plot_key],
                threshold=result["configuration"]["threshold"], unit_reported=finding["reference"]["unit_reported"]),
                width="stretch", key="finding_chart")
            st.caption("The shaded reference envelope is peer median ± threshold × reference spread. "
                       "It is a statistical reference, not an operating specification or confidence interval. "
                       "The highlighted band marks the retained interval; unscoreable reference points remain gaps.")
            first = finding["evidence"][0]
            st.info(f"At {first['time_h']:g} h, the observed value was {first['observed_value']:.6g} {finding['reference']['unit_reported']}, "
                    f"compared with a peer median of {first['reference_median']:.6g} {finding['reference']['unit_reported']} "
                    f"from {first['peer_count']} finite peers. Review the absolute difference alongside the statistical score.")
            st.subheader("Supporting measurements")
            st.caption("Observed values are published simulation measurements. Reference medians, spreads and scores are derived.")
            st.dataframe(demo.evidence_rows(finding), hide_index=True, width="stretch")
            with st.expander("Finite peer support measurements"):
                peers = []
                for point in finding["evidence"]:
                    peers.extend({**row, "source_column_index": finding["reference"]["source_column_index"],
                                  "source_header": finding["reference"]["source_header"]}
                                 for row in point["peer_measurements"])
                st.dataframe(peers, hide_index=True, width="stretch")
            st.subheader("Verified graph provenance")
            st.caption("Directed relationships read from the current Neo4j graph for this batch, variable, artifact and source.")
            st.write("This is the source trail: which batch and variable connect to the prepared data file, and which original source supports them. These relationships describe provenance, not cause and effect.")
            ref = finding["reference"]
            st.caption(f"First interval observation: CSV data row {first['source_row_number']:,} (excluding header), "
                       f"column index {ref['source_column_index']} (zero-based; column {ref['source_column_index'] + 1} when counting from one), "
                       f"exact header {ref['source_header']}.")
            st.dataframe(demo.graph_provenance(driver, finding["reference"], database), hide_index=True, width="stretch")
        st.download_button("Download investigation JSON", data=demo.canonical_json_bytes(result),
            file_name=f"batch_{result['batch']['batch_ref']:03d}_investigation.json", mime="application/json",
            key="download_investigation", on_click="ignore")
        _method(result)
    except Exception as error:
        _clear_current()
        st.error(demo.safe_error_message(error))
        st.markdown("### Continue with the recorded example")
        st.write("The project overview and three recorded cases work without a running database. They explain the workflow using checked-in results, without claiming a fresh live assessment.")
        st.button("Explore the recorded walkthrough", type="primary", on_click=ui.navigate, args=("Recorded walkthrough",))
        with st.expander("Local workspace setup"):
            st.write("Use the repository README to restore the verified data, start the matching local Neo4j runtime and load its graph. Database credentials stay in server-side configuration.")
            st.code(".venv/bin/python scripts/load_graph.py\n.venv/bin/python -m streamlit run app.py", language="bash")


def main():
    view = ui.setup()
    if view == "Project overview":
        ui.overview()
    elif view == "Recorded walkthrough":
        ui.walkthrough()
    elif view == "Data & glossary":
        ui.glossary()
    else:
        workspace()


if __name__ == "__main__":
    main()
