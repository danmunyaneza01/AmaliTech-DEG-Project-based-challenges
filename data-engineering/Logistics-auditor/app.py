"""Veridi Logistics auditor.

Audit overview and Dashboard share one stylesheet, assets/styles.css.
From this folder: streamlit run app.py
"""

import base64
import io
import math
import zipfile
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_loader import load_commerce, load_late_risk, load_state_centers, load_summaries

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "data"

ACCENT = "#0787c2"
DANGER = "#d23b3b"
OK = "#2f8f5b"
WARN = "#ff9332"
ORANGE = "#ff5a00"
INK = "#3e3d3a"
MUTED = "#6f6c66"
GRID = "#e5e7eb"

STATUS_ORDER = ["On Time", "Late", "Super Late", "Not Delivered"]
REVIEW_STATUS_ORDER = ["On Time", "Late", "Super Late"]
DELAY_BIN_ORDER = [
    "8+ days early",
    "1–7 days early",
    "On the promised day",
    "1–5 days late",
    "6–10 days late",
    "11+ days late",
]
REGION_COLORS = {
    "Northeast": DANGER,
    "North": WARN,
    "Central-West": ACCENT,
    "Southeast": OK,
    "South": ORANGE,
}
REGION_FILTERS = ["All regions", "Northeast", "North", "Central-West", "Southeast", "South"]
PAYMENT_LABELS = {
    "credit_card": "Credit card",
    "boleto": "Boleto",
    "voucher": "Voucher",
    "debit_card": "Debit card",
}

st.set_page_config(
    page_title="Logistics Auditor",
    page_icon="L",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def summaries_cached():
    return load_summaries(OUTPUT_DIR)


@st.cache_data
def commerce_cached():
    # Rebuild when the order table used by the dashboard filters changes.
    return load_commerce(DATA_DIR, OUTPUT_DIR)


@st.cache_data
def late_risk_cached():
    return load_late_risk(DATA_DIR, OUTPUT_DIR)


@st.cache_data
def state_centers_cached():
    return load_state_centers(DATA_DIR)


def bind_chart_tools() -> None:
    import streamlit.components.v1 as components

    components.html(
        """
        <script>
        const doc = window.parent.document;
        if (!window.parent.__chartToolsBound) {
          window.parent.__chartToolsBound = true;
          doc.addEventListener("click", function (event) {
            const closest = event.target.closest ? event.target.closest.bind(event.target) : null;
            if (!closest) return;
            if (closest(".modebar")) return;
            const plot = closest(".js-plotly-plot");
            doc.querySelectorAll(".js-plotly-plot.tools-on").forEach(function (node) {
              if (node !== plot) node.classList.remove("tools-on");
            });
            if (plot) plot.classList.toggle("tools-on");
          });
        }
        function lockPlot(gd) {
          const layout = gd._fullLayout;
          const box = layout && (layout.map || layout.mapbox);
          const map = box && box._subplot && box._subplot.map;
          if (!map || map.__viewLocked) return;
          map.__viewLocked = true;
          ["dragPan", "scrollZoom", "boxZoom", "doubleClickZoom", "touchZoomRotate", "keyboard"].forEach(function (name) {
            if (map[name] && map[name].disable) map[name].disable();
          });
        }
        function lockMaps() {
          doc.querySelectorAll(".js-plotly-plot").forEach(lockPlot);
        }
        lockMaps();
        setTimeout(lockMaps, 700);
        </script>
        """,
        height=0,
    )


def inject_css() -> None:
    css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    st.markdown(
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Poppins:wght@500;600;700&display=swap">',
        unsafe_allow_html=True,
    )
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def choose_section(name: str) -> None:
    st.session_state.section = name


def pct(value: float) -> str:
    return f"{value:.1%}"


def category_label(name: str) -> str:
    return name.replace("_", " ").replace(" and ", " & ").title()


CHART_HEIGHT = 380
BAR_SLOTS = 8


def apply_layout(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        height=CHART_HEIGHT,
        font=dict(family='"Poppins", "Inter", "Segoe UI", sans-serif', color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=16, t=40, b=8),
        bargap=0.32,
        bargroupgap=0.08,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(namelength=-1, align="left", font=dict(size=13, color=INK)),
        dragmode=False,
    )
    show_grid = st.session_state.get("section") != "dashboard"
    fig.update_xaxes(automargin=True, showgrid=show_grid, gridcolor=GRID, zeroline=False)
    fig.update_yaxes(automargin=True, showgrid=show_grid, gridcolor=GRID, zeroline=False)
    return fig


def even_bars(fig: go.Figure) -> None:
    """Keep every bar the same thickness, including charts that have only two bars."""
    bars = [trace for trace in fig.data if getattr(trace, "type", None) == "bar"]
    if not bars:
        return
    horizontal = any(getattr(trace, "orientation", None) == "h" for trace in bars)
    labels: list = []
    for trace in bars:
        raw = trace.y if horizontal else trace.x
        categories = [] if raw is None else list(raw)
        for category in categories:
            if category not in labels:
                labels.append(category)
    count = len(labels)
    if count == 0 or count >= BAR_SLOTS:
        return
    pad = (BAR_SLOTS - count) / 2
    axis_range = [-0.5 - pad, count - 0.5 + pad]
    # Keep labels such as 2016 on the category axis. A numeric range would
    # place those bars far outside the window.
    if horizontal:
        fig.update_yaxes(type="category", range=axis_range)
    else:
        fig.update_xaxes(type="category", range=axis_range)


CHART_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "scrollZoom": False,
    "doubleClick": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}


def _series(raw) -> list:
    if raw is None:
        return []
    return list(raw)


def _has_labels(trace) -> bool:
    raw = getattr(trace, "text", None)
    if raw is None:
        return False
    try:
        items = list(raw)
    except TypeError:
        return str(raw) != ""
    return any(item is not None and str(item) != "" for item in items)


def _number_text(value, tickformat: str) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return ""
    if "%" in (tickformat or ""):
        return f"{number:.1%}"
    if number.is_integer() or abs(number) >= 100:
        return f"{number:,.0f}"
    if abs(number) <= 5:
        return f"{number:.2f}"
    return f"{number:.1f}"


def _axis_format(fig: go.Figure, trace, horizontal: bool) -> str:
    if getattr(trace, "yaxis", None) == "y2":
        axis = fig.layout.yaxis2
    elif horizontal:
        axis = fig.layout.xaxis
    else:
        axis = fig.layout.yaxis
    return getattr(axis, "tickformat", None) or ""


def reveal_numbers(fig: go.Figure) -> None:
    """Print the value on the mark. A hover or a click is not required."""
    scatter_rows = 0
    for trace in fig.data:
        kind = getattr(trace, "type", None)
        if kind == "bar":
            horizontal = getattr(trace, "orientation", None) == "h"
            if not _has_labels(trace):
                values = _series(trace.x if horizontal else trace.y)
                tickformat = _axis_format(fig, trace, horizontal)
                trace.text = [_number_text(value, tickformat) for value in values]
            stacked = fig.layout.barmode == "stack"
            trace.textposition = "auto" if stacked else "outside"
            trace.cliponaxis = False
            trace.textfont = dict(size=12, color=INK, family="Poppins, Inter, sans-serif")
        elif kind in {"scatter", "scattergl"} and "lines" in (getattr(trace, "mode", None) or ""):
            values = _series(trace.y)
            if not values or _has_labels(trace):
                continue
            tickformat = _axis_format(fig, trace, False)
            if len(values) > 8:
                labels = [""] * len(values)
                scored = []
                for index, value in enumerate(values):
                    try:
                        number = float(value)
                    except (TypeError, ValueError):
                        continue
                    if not math.isnan(number):
                        scored.append((index, number))
                if scored:
                    peak = max(scored, key=lambda item: item[1])[0]
                    labels[peak] = _number_text(values[peak], tickformat)
                trace.text = labels
            else:
                trace.text = [_number_text(value, tickformat) for value in values]
            trace.mode = "lines+text"
            trace.textposition = "top center" if scatter_rows % 2 == 0 else "bottom center"
            trace.cliponaxis = False
            trace.textfont = dict(size=11, color=getattr(getattr(trace, "line", None), "color", None) or INK)
            scatter_rows += 1
        elif kind == "pie":
            trace.texttemplate = "%{percent:.1%}<br>%{value:,.0f}"
            trace.textposition = "inside"
            trace.textfont = dict(size=12, color="#ffffff", family="Poppins, Inter, sans-serif")
    fig.update_layout(uniformtext=dict(minsize=9, mode="show"), margin=dict(l=8, r=28, t=48, b=12))


def show(fig: go.Figure) -> None:
    reveal_numbers(fig)
    even_bars(fig)
    st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)


def card_heading(title: str, note: str = "") -> None:
    note_html = f'<p class="card-note">{note}</p>' if note else '<p class="card-note"></p>'
    st.markdown(f'<h2 class="card-title">{title}</h2>{note_html}', unsafe_allow_html=True)


def hint(short: str, deep: str) -> None:
    st.markdown(
        f'<div class="hint"><p class="hint-short">{escape(short)}</p><p class="hint-deep">{escape(deep)}</p></div>',
        unsafe_allow_html=True,
    )


def brand_logo() -> str:
    raw = (ROOT / "assets" / "veridi-logo.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def toggle_nav() -> None:
    st.session_state.nav_open = not st.session_state.nav_open


def render_nav() -> None:
    st.session_state.setdefault("nav_open", True)
    if st.session_state.nav_open:
        st.button(
            "Hide",
            key="nav_hide",
            icon=":material/left_panel_close:",
            on_click=toggle_nav,
        )
        sections = (
            ("overview", "Overview"),
            ("delivery", "Delivery Performance"),
            ("dashboard", "Dashboard"),
            ("predict", "Prediction"),
        )
        with st.sidebar:
            st.markdown(
                f'<img class="brand-logo" src="{brand_logo()}" alt="Veridi Logistics">',
                unsafe_allow_html=True,
            )
            for key, label in sections:
                active = st.session_state.section == key
                st.button(
                    label,
                    key=f"nav_{key}",
                    type="primary" if active else "secondary",
                    width="content",
                    on_click=choose_section,
                    args=(key,),
                )
        return
    st.button(
        "Menu",
        key="nav_show",
        icon=":material/left_panel_open:",
        on_click=toggle_nav,
    )


def render_explanation() -> None:
    st.markdown(
        """
        <div class="scene" aria-hidden="true">
          <svg viewBox="0 0 720 96" fill="none">
            <path d="M96 40H624" stroke="#ffbc6d" stroke-width="3"/>
            <circle cx="96" cy="40" r="24" fill="#053762"/>
            <circle cx="360" cy="40" r="24" fill="#ff5a00"/>
            <circle cx="624" cy="40" r="24" fill="#053762"/>
            <g transform="translate(84,28)" stroke="#ffbc6d" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
              <path d="M2 6l10-4 10 4-10 4z"/>
              <path d="M2 6v10l10 4V10"/>
              <path d="M22 6v10l-10 4"/>
            </g>
            <g transform="translate(348,28)" stroke="#fff" stroke-width="1.6" stroke-linecap="round">
              <rect x="3" y="5" width="18" height="15" rx="2"/>
              <path d="M3 9h18M8 3v4M16 3v4"/>
            </g>
            <g transform="translate(612,28)" stroke="#ffbc6d" stroke-width="1.6" stroke-linejoin="round">
              <path d="M12 3l2.2 4.8 5.2.5-3.9 3.4 1.1 5.1L12 14.6 7.4 16.8l1.1-5.1L4.6 8.3l5.2-.5z"/>
            </g>
            <text x="96" y="84" text-anchor="middle" fill="#053762" font-family="Poppins, sans-serif" font-size="13" font-weight="600">Promise</text>
            <text x="360" y="84" text-anchor="middle" fill="#053762" font-family="Poppins, sans-serif" font-size="13" font-weight="600">Arrival</text>
            <text x="624" y="84" text-anchor="middle" fill="#053762" font-family="Poppins, sans-serif" font-size="13" font-weight="600">Review</text>
          </svg>
        </div>
        <div class="method-grid">
          <section class="home-card">
            <h2><i class="mark box"></i>What this audit is</h2>
            <p>A delivery performance audit checks one promise: did the package arrive on the day the customer was told, or after it? It is a review of that promise, not a guess about next month’s sales.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark alert"></i>Why Veridi needs it</h2>
            <p>Reviews got worse. The open question is whether the date on the order is too hopeful in a few parts of Brazil, or across the whole country.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark clock"></i>What “performance” means</h2>
            <p>Performance here is the promised day, not the length of the road by itself. A long trip can still be on time if the date left enough room. A short trip can still be late if the date was too soon.</p>
          </section>
        </div>
        <section class="callout accent">
          <h2><i class="mark calendar"></i>How a day becomes “late”</h2>
          <p>The promised date is the day the customer was given. The actual date is the day the package arrived. Days late are the actual date minus the promised date.</p>
          <p class="audit-example">If Veridi promises that a package will arrive on 10 June, and it arrives on 13 June, the package was 3 days late.</p>
          <p>On time means it arrived on that day or earlier. Most packages here arrive early. Late means it arrived after that day. Regions matter because a calm national average can hide one part of the country. The stars matter because they sit on the same order, so a missed day and a lower score can be read together. A lower score next to a late package is a pattern. It is not, by itself, proof that the delay caused the review.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


ANALYSIS_TABLES = (
    "delivery_status_summary.csv",
    "region_performance.csv",
    "state_performance.csv",
    "review_by_status.csv",
    "review_by_delay_bin.csv",
    "category_performance.csv",
)


@st.cache_data
def analysis_tables_zip() -> bytes:
    """The summary tables this page reads, packed for download."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ANALYSIS_TABLES:
            archive.write(OUTPUT_DIR / name, arcname=name)
    return buffer.getvalue()


@st.cache_data
def joined_dataset() -> bytes:
    """One row per order after customers and reviews are joined."""
    return (OUTPUT_DIR / "joined_orders.csv").read_bytes()


@st.cache_data
def source_archive() -> bytes:
    """The public Olist CSV archive the audit is built from."""
    return (DATA_DIR / "olist.zip").read_bytes()


def render_flow() -> None:
    with st.container(key="page_foot"):
        st.markdown(
            """
            <section class="page-foot">
              <h2><i class="mark route"></i>From raw CSV to the answer</h2>
              <p class="foot-lead">The files start separate. They are cleaned, joined to one row per order, and compared with the promised day. That comparison is the insight on this page.</p>
              <div class="flow">
                <article class="flow-step">
                  <div class="flow-node">01</div>
                  <h3>Raw CSV</h3>
                  <p>Orders, customers, reviews, items, products, and payments start as separate files.</p>
                </article>
                <article class="flow-step">
                  <div class="flow-node">02</div>
                  <h3>Clean</h3>
                  <p>Each order id is kept once. A missing arrival is flagged, not called late.</p>
                </article>
                <article class="flow-step">
                  <div class="flow-node">03</div>
                  <h3>Join</h3>
                  <p>State and one review score are added. Items do not copy the order.</p>
                </article>
                <article class="flow-step">
                  <div class="flow-node">04</div>
                  <h3>Compare</h3>
                  <p>The promised day is set against the arrival day, then the stars.</p>
                </article>
                <article class="flow-step">
                  <div class="flow-node">05</div>
                  <h3>Insight</h3>
                  <p>That one row is what the late rate, the map, and the places to fix first read.</p>
                </article>
              </div>
              <div class="foot-grid">
                <section>
                  <h3><i class="mark check"></i>Cleaned</h3>
                  <p>99,441 orders, and no order id is repeated. 2,971 orders have no arrival day. They stay in the file and are left out of the 6.8% late rate. 547 orders had more than one review, so those scores were averaged first. Every score is from 1 to 5. No package is recorded as arriving before it was bought.</p>
                </section>
                <section>
                  <h3><i class="mark layers"></i>Joined</h3>
                  <p>Orders are the hub. Customers join on customer id, one state per order. Reviews join on order id only after they are one score. Item rows stay beside the order. The English category is the most expensive item, so a basket of several products is still one order.</p>
                </section>
                <section>
                  <h3><i class="mark file"></i>Safe to reuse</h3>
                  <p>One row is one promised delivery. Late means the arrival calendar day is after the promised day. Super late means more than five days after. The five regions are groups of the customer’s state. Payments and map points stay in their own files, so they cannot count the same order twice.</p>
                </section>
              </div>
              <h3 class="foot-download-title"><i class="mark file"></i>Download the data this audit uses</h3>
              <p class="foot-lead">Analysis tables are the six summaries on this page. The joined dataset is one row per order: the order, the customer state, and one review score.</p>
            </section>
            """,
            unsafe_allow_html=True,
        )
        column_count = 3 if (DATA_DIR / "olist.zip").exists() else 2
        columns = st.columns(column_count, gap="small")
        index = 0
        with columns[index]:
            st.download_button(
                "Analysis tables",
                data=analysis_tables_zip(),
                file_name="veridi_analysis_tables.zip",
                mime="application/zip",
                type="primary",
                icon=":material/download:",
                width="stretch",
                help="Delivery status, regions, states, reviews by status, reviews by delay, and categories.",
                key="download_analysis_tables",
            )
        index += 1
        if (OUTPUT_DIR / "joined_orders.csv").exists():
            with columns[index]:
                st.download_button(
                    "Joined dataset",
                    data=joined_dataset(),
                    file_name="joined_orders.csv",
                    mime="text/csv",
                    type="primary",
                    icon=":material/download:",
                    width="stretch",
                    help="99,441 orders. Customers and one review score are already attached.",
                    key="download_joined_dataset",
                )
            index += 1
        if (DATA_DIR / "olist.zip").exists():
            with columns[index]:
                st.download_button(
                    "Source CSV archive",
                    data=source_archive(),
                    file_name="olist_source_files.zip",
                    mime="application/zip",
                    type="primary",
                    icon=":material/download:",
                    width="stretch",
                    help="The public Olist files this audit is built from.",
                    key="download_source_archive",
                )
        st.markdown(
            '<p class="foot">Source: Olist public orders, customers, reviews, and items. Purchases from 4 September 2016 to 17 October 2018.</p>',
            unsafe_allow_html=True,
        )


def render_method() -> None:
    st.markdown(
        """
        <h2 class="section-label"><i class="mark shield"></i>What this audit cannot prove</h2>
        <div class="method-grid">
          <section class="home-card">
            <h2><i class="mark shield"></i>Limits</h2>
            <p>This is the Olist public history. Purchases run from 4 September 2016 to 17 October 2018. It is not a live feed. The 6.8% late rate counts packages that arrived. The 2,971 orders with no arrival are left out of that rate, and they are not called late.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark pin"></i>Cause</h2>
            <p>The audit shows where the promised day is missed, and that the extra time is on the road after the carrier has the package. It does not show why the road is slow. Carrier contracts, routes, staffing, and season are not in this table.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark file"></i>What you can open</h2>
            <p>The notebook is the working record. This page is the audit. Dashboard is sales and payments. Prediction flags orders that are more likely to miss the date. The notebook, the chart export, and the slides are linked from Overview.</p>
          </section>
        </div>
        """,
        unsafe_allow_html=True,
    )


def national_figures(status: pd.DataFrame, by_status: pd.DataFrame) -> dict:
    status_ix = status.set_index("delivery_status")
    scores = by_status.set_index("delivery_status")
    delivered = int(status_ix.loc[REVIEW_STATUS_ORDER, "orders"].sum())
    late_orders = int(status_ix.loc[["Late", "Super Late"], "orders"].sum())
    late_reviewed = scores.loc[["Late", "Super Late"]]
    late_score = float((late_reviewed["orders"] * late_reviewed["avg_review_score"]).sum() / late_reviewed["orders"].sum())
    return {
        "delivered": delivered,
        "late_rate": late_orders / delivered,
        "super_late_rate": float(status_ix.loc["Super Late", "orders"] / delivered),
        "not_delivered": int(status_ix.loc["Not Delivered", "orders"]),
        "on_time_score": float(scores.loc["On Time", "avg_review_score"]),
        "late_score": late_score,
        "super_late_score": float(scores.loc["Super Late", "avg_review_score"]),
    }


def render_scenario(summaries: dict, commerce: dict | None, national: dict) -> None:
    """Pictures for the CEO's question. Added beside the audit, not in place of it."""
    by_bin = summaries["review_by_delay_bin"].set_index("delay_bin").loc[DELAY_BIN_ORDER].reset_index()
    regions = summaries["region_performance"].sort_values("late_rate", ascending=False)
    st.markdown(
        """
        <h2 class="section-label"><i class="mark route"></i>The scenario</h2>
        <p class="audit-note">Reviews got worse. The suspicion is that the date on the order is wildly too soon, and that this is true across Brazil. These pictures use the same rules as the rest of the page. They do not replace the tables below.</p>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        card_heading(
            "Is the promised day wildly too soon?",
            "Orders with a review. Most of the bars are early. The late bars are the tail, so the typical date is not too soon.",
        )
        early_colors = [OK, OK, ACCENT, WARN, DANGER, DANGER]
        fig = go.Figure(go.Bar(
            x=by_bin["delay_bin"],
            y=by_bin["orders"],
            marker_color=early_colors,
            hovertemplate="%{x}<br>%{y:,} orders<extra></extra>",
        ))
        apply_layout(fig)
        fig.update_layout(showlegend=False, yaxis_title="Orders with a review")
        show(fig)

    on_time_rate, late_rate = 0.0923, 0.6236
    on_time_neg, late_neg = 8257, 3979
    if commerce is not None:
        reviewed = commerce["frame"]
        reviewed = reviewed.loc[reviewed["review_score"].notna() & reviewed["is_late"].notna()]
        on_time = reviewed.loc[reviewed["is_late"] == False]
        late = reviewed.loc[reviewed["is_late"] == True]
        on_time_rate = float((on_time["review_score"] <= 2).mean())
        late_rate = float((late["review_score"] <= 2).mean())
        on_time_neg = int((on_time["review_score"] <= 2).sum())
        late_neg = int((late["review_score"] <= 2).sum())
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            card_heading(
                "A late package sits next to a weaker review",
                "Share of orders with a review that scored 1 or 2 stars. This is a pattern, not proof that the delay caused the score.",
            )
            fig = go.Figure(go.Bar(
                x=["On time", "Late"],
                y=[on_time_rate, late_rate],
                marker_color=[OK, DANGER],
                text=[pct(on_time_rate), pct(late_rate)],
                textposition="outside",
            ))
            apply_layout(fig)
            fig.update_layout(showlegend=False, yaxis_title="1- or 2-star reviews", yaxis_tickformat=".0%", yaxis_range=[0, 0.85])
            show(fig)
    with right:
        with st.container(border=True):
            card_heading(
                "Most weak reviews are still on time",
                "Count of 1- and 2-star reviews. Most orders arrive on time, so most weak reviews do too. A later date does not clear the spike by itself.",
            )
            fig = go.Figure(go.Bar(
                x=["On time", "Late"],
                y=[on_time_neg, late_neg],
                marker_color=[OK, DANGER],
                text=[f"{on_time_neg:,}", f"{late_neg:,}"],
                textposition="outside",
            ))
            apply_layout(fig)
            fig.update_layout(showlegend=False, yaxis_title="Weak reviews")
            show(fig)

    with st.container(border=True):
        card_heading(
            "Is the miss in every region, or in some?",
            "The dashed line is the country, 6.8% late. Bars above it are worse than the country. The map further down shows the states inside these regions.",
        )
        fig = go.Figure(go.Bar(
            x=regions["region"],
            y=regions["late_rate"],
            marker_color=[REGION_COLORS.get(name, MUTED) for name in regions["region"]],
            text=[pct(value) for value in regions["late_rate"]],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:.1%}<extra></extra>",
        ))
        fig.add_hline(y=national["late_rate"], line_dash="dash", line_color=INK)
        apply_layout(fig)
        fig.update_layout(showlegend=False, yaxis_title="Late rate", yaxis_tickformat=".0%", yaxis_range=[0, 0.18])
        show(fig)


def render_data_notes() -> None:
    st.markdown(
        """
        <h2 class="section-label"><i class="mark layers"></i>The data, and what was kept out</h2>
        <div class="method-grid">
          <section class="home-card">
            <h2><i class="mark layers"></i>What each field means</h2>
            <p>An order id is one package’s promise. The customer state is where it was delivered, grouped into five regions. The estimated date is the day the customer was given. The actual date is the day it arrived. The review score is the stars, from 1 to 5.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark check"></i>99,441 orders, each once</h2>
            <p>There are no duplicate order ids. Purchases run from 4 September 2016 to 17 October 2018. Every order has an estimated date. No package is recorded as arriving before it was bought. Every review score is between 1 and 5.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark alert"></i>2,971 orders are not in the late rate</h2>
            <p>They were canceled, unavailable, still moving, or have no arrival day. Eight are marked delivered but have no arrival date. They stay in the file and are not called late. 547 orders had more than one review, out of 99,224 review rows and 98,673 orders. Those scores were averaged so the order is counted once.</p>
          </section>
        </div>
        <p class="audit-note">Extreme delays were kept. The longest miss is 188 days. 2,299 arrived packages are 10 or more days late. They were not deleted.</p>
        """,
        unsafe_allow_html=True,
    )


def render_audit(summaries: dict, commerce: dict | None) -> None:
    status = summaries["delivery_status_summary"]
    states = summaries["state_performance"]
    regions = summaries["region_performance"]
    by_status = summaries["review_by_status"]
    by_bin = summaries["review_by_delay_bin"]
    national = national_figures(status, by_status)
    st.markdown('<h2 class="section-label"><i class="mark chart"></i>The proof</h2>', unsafe_allow_html=True)
    render_scenario(summaries, commerce, national)
    st.markdown('<h2 class="section-label"><i class="mark chart"></i>Company-wide performance</h2>', unsafe_allow_html=True)

    on_time = 1 - national["late_rate"]
    kpis = [
        ("box", "Delivered orders", f"{national['delivered']:,}", "Packages with an arrival day"),
        ("check", "On-time rate", pct(on_time), "On the promised day or earlier"),
        ("clock", "Late rate", pct(national["late_rate"]), f"More than five days late: {pct(national['super_late_rate'])}"),
        ("calendar", "Median arrival", "12 days early", "Half of deliveries are at least this early"),
        ("alert", "When it is late", "7 days", "Median delay. The average is 10.6 days"),
        ("star", "On-time review", f"{national['on_time_score']:.2f}", "Stars out of 5"),
    ]
    cards = "".join(
        f'<div class="kpi"><i class="mark {mark}"></i><span>{escape(label)}</span><b>{escape(value)}</b><i>{escape(note)}</i></div>'
        for mark, label, value, note in kpis
    )
    st.markdown(f'<div class="kpis">{cards}</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <p class="audit-note">On time means the package arrived on the promised calendar day or before it. Late means after that day. Of the late packages, those more than five days late are called super late. The median is used beside the average because a few very long delays pull the average up. The average delay among late packages is 10.6 days. The median is 7.</p>
        <h2 class="section-label"><i class="mark clock"></i>How late is grouped</h2>
        <p class="audit-note">The groups follow the point where the stars break, not a 1–2 day and 3–5 day split. Stars stay near 4 while the package is early. They fall to 2.99 when it is 1 to 5 days late, and to about 1.7 once the delay passes 5 days. Early packages are still shown in finer bands so a long trip that arrives early is not called a failure.</p>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<h2 class="section-label"><i class="mark pin"></i>Regions, not one national average</h2>', unsafe_allow_html=True)
    delay = {
        "Northeast": (12.4, 8, 166),
        "North": (13.5, 7, 165),
        "Southeast": (10.4, 6, 188),
        "Central-West": (9.4, 6, 152),
        "South": (9.1, 6, 155),
    }
    table_rows = []
    for row in regions.sort_values("late_rate", ascending=False).itertuples(index=False):
        mean_late, median_late, max_late = delay[row.region]
        table_rows.append(
            "<tr>"
            f"<td>{escape(row.region)}</td>"
            f"<td>{int(row.delivered_orders):,}</td>"
            f"<td>{pct(1 - row.late_rate)}</td>"
            f"<td>{pct(row.late_rate)}</td>"
            f"<td>{mean_late:.1f}</td>"
            f"<td>{median_late}</td>"
            f"<td>{max_late}</td>"
            f"<td>{row.avg_review_score:.2f}</td>"
            "</tr>"
        )
    st.markdown(
        '<div class="table-wrap"><table class="audit-table"><thead><tr>'
        "<th>Region</th><th>Deliveries</th><th>On time</th><th>Late</th>"
        "<th>Avg days late</th><th>Median days late</th><th>Longest delay</th><th>Avg rating</th>"
        f"</tr></thead><tbody>{''.join(table_rows)}</tbody></table></div>"
        '<p class="audit-note">On time and late use every package that arrived. Average days late, the median, and the longest delay count only packages that missed the promised day. A small region can post a high rate on few orders. São Paulo is 4.5% late on 40,494 deliveries. Rio de Janeiro is 12.1% on 12,350. Alagoas is 21.4% on 397. Roraima (41), Acre (80), and Amapá (67) have fewer than 100 deliveries, so those rates are low-confidence. Ranked by late parcels times the share of 1- and 2-star reviews, Rio is first and São Paulo is second: São Paulo’s rate is low, and its misses are still numerous. The South, Southeast, and Central-West sit at or under the national 6.8%. The Northeast is about twice the Southeast. The North is only a little above the country, after a wider promised day. Packages that stay in the seller’s state are late 4.5% of the time (34,690 deliveries). Packages that cross a state line are late 8.0% of the time (61,780).</p>',
        unsafe_allow_html=True,
    )

    st.markdown('<h3 class="group-label">Was the promised day too soon?</h3>', unsafe_allow_html=True)
    with st.container(border=True):
        card_heading("Promised days versus the days the trip actually took")
        hint(
            "We did not give the Northeast enough extra days for a longer trip.",
            "Blue is the day we promised. Red is how long the trip really took. In most of Brazil the trip is shorter than the promise, so the package arrives early. The Northeast trip takes about twice as long as the Southeast trip, and we only added a few extra days to the date. That is why more packages there arrive late. In the North we promised more extra days, and fewer packages miss the day, even though the road is long.",
        )
        scoped = regions.sort_values("avg_actual_lead_days")
        fig = go.Figure()
        fig.add_bar(name="Promised", x=scoped["region"], y=scoped["avg_promised_lead_days"], marker_color=ACCENT)
        fig.add_bar(name="Actual", x=scoped["region"], y=scoped["avg_actual_lead_days"], marker_color=DANGER)
        apply_layout(fig)
        fig.update_layout(barmode="group", yaxis_title="Days from purchase")
        show(fig)

    st.markdown('<h3 class="group-label">Do the stars follow a missed day?</h3>', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            card_heading("Review score against the promised date")
            hint(
                "Stars stay high while the package is early, then fall once it is late.",
                "If the package arrives before the day we promised, customers still give about 4 stars. Once it is late, the stars drop, and they drop again after five days. Customers who wait longer tend to leave lower ratings. The data shows that the two move together. It does not prove the delay was the only reason for the review.",
            )
            bins = by_bin.set_index("delay_bin").loc[DELAY_BIN_ORDER].reset_index()
            colors = [OK, OK, OK, WARN, DANGER, DANGER]
            fig = go.Figure(go.Bar(
                x=bins["delay_bin"],
                y=bins["avg_review_score"],
                marker_color=colors,
                customdata=bins["orders"],
                hovertemplate="%{x}<br>%{y:.2f}<br>%{customdata:,} reviews<extra></extra>",
            ))
            apply_layout(fig)
            fig.update_layout(showlegend=False, yaxis_range=[1, 5], yaxis_title="Average review")
            show(fig)
    with right:
        with st.container(border=True):
            if commerce is not None:
                card_heading("Where the extra days go")
                hint(
                    "The extra days are on the road, after the delivery company has the package.",
                    "The shop’s part is short: pack the order until the delivery company picks it up. That stays short even when the package is late. The long part is the road. Late packages spend many more days with the delivery company. The day we showed the customer did not leave enough time for that.",
                )
                stages = commerce["stages"].set_index("group").loc[["On time", "Late"]].reset_index()
                fig = go.Figure()
                fig.add_bar(name="Seller handling", y=stages["group"], x=stages["handling_days"], orientation="h", marker_color=ACCENT)
                fig.add_bar(name="Carrier transit", y=stages["group"], x=stages["transit_days"], orientation="h", marker_color=DANGER)
                apply_layout(fig)
                fig.update_layout(barmode="stack", xaxis_title="Days")
                show(fig)
            else:
                card_heading("Review score by status")
                scores = by_status.set_index("delivery_status").loc[REVIEW_STATUS_ORDER].reset_index()
                fig = go.Figure(go.Bar(
                    x=scores["delivery_status"],
                    y=scores["avg_review_score"],
                    marker_color=[OK, WARN, DANGER],
                    text=[f"{value:.2f}" for value in scores["avg_review_score"]],
                    textposition="outside",
                ))
                apply_layout(fig)
                fig.update_layout(showlegend=False, yaxis_range=[1, 5.4])
                show(fig)

    st.markdown('<h3 class="group-label">Is it the whole country, or some places?</h3>', unsafe_allow_html=True)
    with st.container(border=True):
        card_heading("Are we failing regions, or the whole country?")
        sao = states.loc[states["customer_state"] == "SP"].iloc[0]
        rio = states.loc[states["customer_state"] == "RJ"].iloc[0]
        country_late = float(national["late_rate"])
        try:
            centers = state_centers_cached()
        except FileNotFoundError:
            centers = None
        if centers is None:
            picture = "Each bar is a state. The color is its region. The length is the share of arrived packages that missed the promised day."
            place = "São Paulo is the shortest large bar"
            rio_place = "Rio is a long bar"
        else:
            picture = f"Each dot is a state. The color is its region. A bigger dot has more orders. A dark ring means that state misses the promised day more often than Brazil ({pct(country_late)})."
            place = "São Paulo is the biggest dot and has no ring"
            rio_place = "Rio has a large ring"
        st.markdown(
            f"""
            <p class="audit-note">No. The miss is in some states, not in every state. {picture}</p>
            <p class="audit-note">{place}: {pct(sao["late_rate"])} late on {int(sao["delivered_orders"]):,} orders. {rio_place}: {pct(rio["late_rate"])} late on {int(rio["delivered_orders"]):,} orders. The higher rates are mainly in the Northeast and in Rio.</p>
            """,
            unsafe_allow_html=True,
        )
        if st.session_state.get("geo_focus") == "Repair first":
            st.session_state.geo_focus = "Worse than Brazil"
        with st.container(key="map_filters"):
            region_col, focus_col = st.columns(2, gap="small")
            with region_col:
                map_region = st.selectbox("Region", REGION_FILTERS, key="geo_region", width=180)
            with focus_col:
                map_focus = st.selectbox("Show", ["All states", "Worse than Brazil"], key="geo_focus", width=210)
        keys = "".join(
            f'<span class="map-key"><i style="background:{color}"></i>{escape(name)}</span>'
            for name, color in REGION_COLORS.items()
        )
        if centers is None:
            st.markdown(
                f'<div class="map-legend">{keys}<span class="map-key note">Bar length = late share of arrived packages</span></div>',
                unsafe_allow_html=True,
            )
            chart_states = states.copy()
            if map_region != "All regions":
                chart_states = chart_states.loc[chart_states["region"] == map_region]
            if map_focus == "Worse than Brazil":
                chart_states = chart_states.loc[chart_states["late_rate"] > country_late]
            if chart_states.empty:
                st.info("No state in this view misses the promised day more often than Brazil.")
            else:
                chart_states = chart_states.sort_values("late_rate", ascending=True)
                fig = go.Figure(go.Bar(
                    y=chart_states["customer_state"],
                    x=chart_states["late_rate"],
                    orientation="h",
                    marker_color=[REGION_COLORS.get(name, MUTED) for name in chart_states["region"]],
                    text=[
                        f"{pct(value)} · {int(count):,}"
                        for value, count in zip(chart_states["late_rate"], chart_states["delivered_orders"])
                    ],
                    textposition="outside",
                    hovertemplate="%{y}<br>%{text}<extra></extra>",
                ))
                apply_layout(fig)
                fig.update_layout(
                    showlegend=False,
                    height=max(380, 22 * len(chart_states) + 80),
                    xaxis_tickformat=".0%",
                    xaxis_title="Late rate",
                    xaxis_range=[0, max(float(chart_states["late_rate"].max()) * 1.55, 0.2)],
                    yaxis=dict(
                        categoryorder="array",
                        categoryarray=list(chart_states["customer_state"]),
                    ),
                )
                show(fig)
        else:
            st.markdown(
                f'<div class="map-legend">{keys}<span class="map-key note">Bigger dot = more orders</span><span class="map-key note">Dark ring = worse than Brazil</span></div>',
                unsafe_allow_html=True,
            )
            mapped = states.merge(centers, on="customer_state", how="inner")
            if map_region != "All regions":
                mapped = mapped.loc[mapped["region"] == map_region]
            national_late = float(national["late_rate"])
            if map_focus == "Worse than Brazil":
                mapped = mapped.loc[mapped["late_rate"] > national_late]
            if mapped.empty:
                st.info("No state in this view misses the promised day more often than Brazil.")
            else:
                span = float(states["delivered_orders"].max()) or 1
                if map_region == "All regions" and map_focus == "All states":
                    center = dict(lat=-14.2, lon=-51.9)
                    zoom = 3.4
                else:
                    lat_span = float(mapped["lat"].max() - mapped["lat"].min())
                    lon_span = float(mapped["lng"].max() - mapped["lng"].min())
                    view_span = max(lat_span, lon_span * 0.85, 1.5)
                    center = dict(
                        lat=round(float(mapped["lat"].mean()), 2),
                        lon=round(float(mapped["lng"].mean()), 2),
                    )
                    zoom = round(min(5.6, max(3.6, 8.4 - math.log2(view_span))), 1)
                fig = go.Figure()
                repair_rows = mapped.loc[mapped["late_rate"] > national_late]
                if not repair_rows.empty:
                    fig.add_trace(go.Scattermap(
                        lat=repair_rows["lat"],
                        lon=repair_rows["lng"],
                        mode="markers",
                        showlegend=False,
                        hoverinfo="skip",
                        marker=dict(
                            size=24 + 22 * repair_rows["delivered_orders"] / span,
                            color=INK,
                        ),
                    ))
                for region_name, color in REGION_COLORS.items():
                    part = mapped.loc[mapped["region"] == region_name]
                    if part.empty:
                        continue
                    repair = part["late_rate"] > national_late
                    fig.add_trace(go.Scattermap(
                        name=region_name,
                        lat=part["lat"],
                        lon=part["lng"],
                        text=[f"{code} {rate:.1%}" for code, rate in zip(part["customer_state"], part["late_rate"])],
                        mode="markers+text",
                        textposition="top center",
                        textfont=dict(size=11, color=INK, family="Poppins, Inter, sans-serif"),
                        customdata=list(zip(
                            part["late_rate"],
                            part["delivered_orders"],
                            part["avg_review_score"],
                            ["Worse than Brazil" if flag else "At or under Brazil" for flag in repair],
                        )),
                        hovertemplate=(
                            "<b>%{text}</b><br>" + region_name + "<br>%{customdata[3]}"
                            "<br>Late %{customdata[0]:.1%}<br>%{customdata[1]:,} orders"
                            "<br>Review %{customdata[2]:.2f}<extra></extra>"
                        ),
                        marker=dict(
                            size=16 + 22 * part["delivered_orders"] / span,
                            color=color,
                        ),
                        showlegend=False,
                    ))
                fig.update_layout(
                    height=560,
                    font=dict(family='"Poppins", "Inter", "Segoe UI", sans-serif', color=INK, size=13),
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=0, b=0),
                    dragmode=False,
                    uirevision=f"{map_region}-{map_focus}",
                    hoverlabel=dict(namelength=-1, align="left", font=dict(size=13, color="#3e3d3a")),
                    showlegend=False,
                    map=dict(style="open-street-map", center=center, zoom=zoom),
                )
                show(fig)

    st.markdown('<h2 class="section-label"><i class="mark trend"></i>Over time</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="audit-note">Purchases run from September 2016 through October 2018. September 2016 and December 2016 have one delivered order each, so the monthly view starts in January 2017 and ends in August 2018. The late rate is 12.4% in November 2017, 14.1% in February 2018, and 19.0% in March 2018, then 4.5% in April 2018. The share of 1- and 2-star reviews moves with it, from 16.5% to 21.1% and back to 11.7%. The spike rises and falls. It is not a single bad month, and it is not a straight climb. When the two lines move together, the missed day and the weak review show up in the same months. That is a pattern, not a cause.</p>',
        unsafe_allow_html=True,
    )
    if commerce is not None and "monthly" in commerce:
        with st.container(border=True):
            card_heading("Late deliveries and weak reviews by month")
            trend = commerce["monthly"]
            fig = go.Figure()
            fig.add_scatter(name="Late deliveries", x=trend["month"], y=trend["late_rate"], mode="lines", line=dict(color=DANGER, width=2))
            fig.add_scatter(name="Reviews of 1 or 2 stars", x=trend["month"], y=trend["negative_share"], mode="lines", line=dict(color=ACCENT, width=2))
            apply_layout(fig)
            fig.update_yaxes(tickformat=".0%", title="Share of orders")
            show(fig)
    else:
        st.info("The monthly view needs the order files in data/.")

    st.markdown(
        """
        <h2 class="section-label"><i class="mark alert"></i>Unusual delays</h2>
        <section class="callout accent">
          <p>The median late package is 7 days late. 2,299 packages are 10 or more days late, and the longest is 188 days. Those rows were kept. They may be real failures or a wrong date. They pull the average delay from 7 days up to 10.6. They do not create the regional result. The late rate counts a one-day miss and a 188-day miss as one miss each, and the Northeast is still about twice the Southeast.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_answer(summaries: dict) -> None:
    status = summaries["delivery_status_summary"].set_index("delivery_status")
    states = summaries["state_performance"].set_index("customer_state")
    regions = summaries["region_performance"].set_index("region")
    delivered = int(status.loc[["On Time", "Late", "Super Late"], "orders"].sum())
    late = int(status.loc[["Late", "Super Late"], "orders"].sum())
    northeast = regions.loc["Northeast"]
    southeast = regions.loc["Southeast"]
    rio = states.loc["RJ"]
    sao = states.loc["SP"]
    st.markdown(
        f"""
        <h2 class="section-label"><i class="mark file"></i>Executive summary</h2>
        <section class="callout accent">
          <p>Of {delivered:,} packages that arrived, {pct(late / delivered)} missed the promised day. The typical package still arrived 12 days early, so the promised date is not too soon for Brazil as a whole. It is too soon in specific places. The Northeast is late {pct(northeast["late_rate"])} of the time, against {pct(southeast["late_rate"])} in the Southeast. Rio de Janeiro is late {pct(rio["late_rate"])} of the time on {int(rio["delivered_orders"]):,} deliveries. São Paulo is late {pct(sao["late_rate"])} on {int(sao["delivered_orders"]):,}. Among orders with a review, a late package is paired with a 1- or 2-star review 62.4% of the time, against 9.2% when the package is on time. Even so, 67.5% of those weak reviews are on-time orders, because most orders are on time. The problem is regional, not nationwide. The over-promising hypothesis holds in the Northeast and in Rio, where the trip is longer and the cushion was not. It does not hold for the typical order.</p>
        </section>
        <h2 class="section-label"><i class="mark route"></i>The answer</h2>
        <section class="callout accent">
          <p>The audit identifies where the performance problem occurs. The extra days are on the road, after the carrier has the package, not in the shop’s packing time. Additional operational data is required to establish the underlying cause. Carrier performance, route, distance, and capacity are not proven by these dates.</p>
          <p><b>The question was whether specific regions are failing, or the whole country.</b> The evidence says specific places. The Northeast misses about twice as often as the Southeast. Rio is a large miss inside an otherwise steadier Southeast. The North, given a wider promised day, misses less often on a long road. São Paulo, the largest state, stays mostly on time. The date shown to the customer is the lever this history can support.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_actions(summaries: dict) -> None:
    status = summaries["delivery_status_summary"].set_index("delivery_status")
    states = summaries["state_performance"].set_index("customer_state")
    regions = summaries["region_performance"].set_index("region")
    delivered = int(status.loc[["On Time", "Late", "Super Late"], "orders"].sum())
    late = int(status.loc[["Late", "Super Late"], "orders"].sum())
    northeast = regions.loc["Northeast"]
    southeast = regions.loc["Southeast"]
    rio = states.loc["RJ"]
    sao = states.loc["SP"]
    st.markdown(
        f"""
        <h2 class="section-label"><i class="mark check"></i>Key findings</h2>
        <section class="callout accent">
          <ol>
            <li>Of {delivered:,} packages that arrived, {late:,} missed the promised day. That is {pct(late / delivered)}. {int(status.loc["Super Late", "orders"]):,} of those misses were more than five days late.</li>
            <li>The typical package is early. The median arrival is 12 days before the promised day. Among packages that were late, the median delay is 7 days and the average is 10.6 days, because a long tail pulls the average up.</li>
            <li>This is not the whole country. The South is {pct(regions.loc["South", "late_rate"])}, the Southeast {pct(southeast["late_rate"])}, and the Central-West {pct(regions.loc["Central-West", "late_rate"])}. The Northeast is {pct(northeast["late_rate"])} on {int(northeast["delivered_orders"]):,} deliveries.</li>
            <li>São Paulo is {pct(sao["late_rate"])} on {int(sao["delivered_orders"]):,} deliveries. Rio de Janeiro is {pct(rio["late_rate"])} on {int(rio["delivered_orders"]):,}. The Southeast average looks calm because São Paulo is large.</li>
            <li>Longer delays sit next to lower stars: 4.29 on time, 2.99 when the package is one to five days late, and 1.74 when it is more than five days late. That is an association, not proof that the delay caused the review.</li>
            <li>The promised day looks tight where the road is long and the cushion was not widened. The Northeast trip takes about {northeast["avg_actual_lead_days"]:.0f} days with about {northeast["avg_days_difference"]:.0f} days of cushion. The Southeast trip takes about {southeast["avg_actual_lead_days"]:.0f} days with about {southeast["avg_days_difference"]:.0f} days of cushion.</li>
          </ol>
        </section>
        <h2 class="section-label"><i class="mark flag"></i>What to do first</h2>
        <div class="recommend-grid">
          <section class="home-card">
            <h2><i class="mark pin"></i>1. A later day in the Northeast and in Rio</h2>
            <p>The Northeast is late {pct(northeast["late_rate"])} on {int(northeast["delivered_orders"]):,} deliveries, with about {northeast["avg_days_difference"]:.0f} days of cushion on a {northeast["avg_actual_lead_days"]:.0f}-day trip. Rio is late {pct(rio["late_rate"])} on {int(rio["delivered_orders"]):,}. The North was given a wider day and misses less often on a long road. The impact is those misses, not a promise to cut the rate by a set amount.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark route"></i>2. A later day when the package leaves the state</h2>
            <p>Same-state deliveries are late 4.5% of the time (34,690). Cross-state deliveries are late 8.0% of the time (61,780). The estimate can treat a package that stays in the seller’s state differently from one that crosses a line. This is a pattern in the dates, not proof of why the road is slower.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark alert"></i>3. Do not rank small states by rate alone</h2>
            <p>Alagoas is 21.4% late on 397 deliveries. Roraima, Acre, and Amapá have fewer than 100. Rio ranks first when late parcels are weighed by the share of weak reviews. São Paulo ranks second because the count of misses is large, even though the rate is 4.5%.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark star"></i>4. The date will not clear every weak review</h2>
            <p>Of 12,236 reviews scored 1 or 2, 8,257 (67.5%) are on-time orders and 3,979 (32.5%) are late. A later promised day addresses the late share. The on-time share needs a separate look at product, seller, and price. This file does not show which of those is responsible.</p>
          </section>
        </div>
        <h2 class="section-label"><i class="mark alert"></i>What would change the answer</h2>
        <section class="callout accent">
          <ul>
            <li>If the Northeast late rate sat near the Southeast’s {pct(southeast["late_rate"])}, this would not be a regional miss.</li>
            <li>If the typical package were late instead of 12 days early, over-promising would be a nationwide description.</li>
            <li>If on-time orders were negative about 62% of the time, as late orders are, the promised day would not be the link to the stars.</li>
            <li>If same-state and cross-state late rates were the same, leaving the seller’s state would drop out of the story.</li>
          </ul>
        </section>
        """,
        unsafe_allow_html=True,
    )


def slice_orders(frame: pd.DataFrame, region: str, year: str, delivery: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    scoped = frame
    if region != "All regions":
        scoped = scoped.loc[scoped["region"] == region]
    if year != "All years":
        scoped = scoped.loc[scoped["year"] == int(year)]
    view = scoped
    if delivery == "On time":
        view = view.loc[view["is_late"] == False]
    elif delivery == "Late":
        view = view.loc[view["is_late"] == True]
    return view, scoped


def money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"R$ {value / 1e6:.1f}M"
    if abs(value) >= 1_000:
        return f"R$ {value / 1e3:.0f}k"
    return f"R$ {value:.0f}"


def render_dashboard(commerce: dict, summaries: dict) -> None:
    st.markdown('<h1 class="page-title"><i class="mark chart"></i>Dashboard</h1>', unsafe_allow_html=True)
    with st.container(border=True, key="dash_panel"):
        brief_slot = st.empty()
        with st.container(key="dash_filters"):
            st.markdown(
                '<p class="filter-kicker"><i class="mark layers"></i>Narrow this selection</p>',
                unsafe_allow_html=True,
            )
            region_col, year_col, delivery_col = st.columns(3, gap="small")
            with region_col:
                dash_region = st.selectbox("Region", REGION_FILTERS, key="dash_region", width="stretch")
            with year_col:
                dash_year = st.selectbox("Year", ["All years", "2016", "2017", "2018"], key="dash_year", width="stretch")
            with delivery_col:
                dash_delivery = st.selectbox("Delivery", ["All orders", "On time", "Late"], key="dash_delivery", width="stretch")
            st.markdown(
                '<p class="audit-note">Sales, reviews, and payments follow all three filters. Late-rate charts use region and year only, so choosing Late does not turn every rate into 100%.</p>',
                unsafe_allow_html=True,
            )
        view, scoped = slice_orders(commerce["frame"], dash_region, dash_year, dash_delivery)
        if view.empty:
            brief_slot.info("No orders match these filters.")
            return
    reviewed = view.loc[view["review_score"].notna()]
    scope_delivered = scoped.loc[scoped["is_late"].notna()]
    scope_late = float(scope_delivered["is_late"].mean()) if not scope_delivered.empty else float("nan")
    on_time_score = float(view.loc[view["is_late"] == False, "review_score"].mean())
    late_score = float(view.loc[view["is_late"] == True, "review_score"].mean())
    repeat_customers = view.groupby("customer_unique_id").size()
    repeat_rate = float((repeat_customers > 1).mean()) if not repeat_customers.empty else float("nan")
    avg_delivery = float(view["actual_days"].mean()) if view["actual_days"].notna().any() else float("nan")
    avg_review = float(reviewed["review_score"].mean()) if not reviewed.empty else float("nan")
    revenue = float(view["price"].sum())

    regions = (
        view.groupby("region", as_index=False)
        .agg(revenue=("price", "sum"), orders=("order_id", "nunique"))
        .merge(
            scope_delivered.groupby("region", as_index=False).agg(
                delivered=("order_id", "size"),
                late_rate=("is_late", "mean"),
            ),
            on="region",
            how="outer",
        )
    )
    regions = regions.loc[regions["region"].isin(REGION_COLORS)].copy()
    regions["revenue"] = regions["revenue"].fillna(0.0)
    score_bits = []
    if on_time_score == on_time_score:
        score_bits.append(f"On-time orders score {on_time_score:.2f}")
    if late_score == late_score:
        score_bits.append(f"orders that missed the day score {late_score:.2f}, mixing a short miss and a long one")
    score_line = ". ".join(score_bits) + "." if score_bits else ""
    if regions.empty or regions["revenue"].sum() == 0:
        place_line = ""
    else:
        leader = regions.loc[regions["revenue"].idxmax()]
        leader_share = float(leader["revenue"] / regions["revenue"].sum())
        eligible = regions.loc[regions["delivered"].fillna(0) >= 100]
        if eligible.empty:
            place_line = f"{leader['region']} holds {pct(leader_share)} of sales in this selection."
        else:
            worst = eligible.loc[eligible["late_rate"].idxmax()]
            place_line = (
                f"{leader['region']} holds {pct(leader_share)} of sales ({money(float(leader['revenue']))}). "
                f"{worst['region']} misses the date most often among regions with at least 100 deliveries: "
                f"{pct(float(worst['late_rate']))} on {int(worst['delivered']):,}."
            )
    late_line = f" Of packages that arrived in this region and year, {pct(scope_late)} missed the promised day." if scope_late == scope_late else ""
    brief_slot.markdown(
        f"""
        <div class="dash-brief">
          <h2><i class="mark flag"></i>Dashboard brief</h2>
          <p>This selection is {money(revenue)} in product sales across {view['order_id'].nunique():,} orders. {score_line}{late_line} {place_line} A later promised day belongs where the miss is concentrated, not on every order in the selection.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kpis = [
        ("chart", "tone-navy", "Total revenue", money(revenue), "Product sales, excludes freight"),
        ("box", "tone-blue", "Orders", f"{view['order_id'].nunique():,}", "Orders in this selection"),
        ("users", "tone-orange", "Unique customers", f"{view['customer_unique_id'].nunique():,}", "Distinct customers in this selection"),
        ("file", "tone-rust", "Avg order value", f"R$ {view['price'].mean():.0f}", "Product sales per order"),
        ("star", "tone-green", "Avg review score", f"{avg_review:.2f}" if avg_review == avg_review else "—", "Orders with a review, out of 5"),
        ("clock", "tone-amber", "Avg delivery time", f"{avg_delivery:.1f} days" if avg_delivery == avg_delivery else "—", "Purchase to delivery"),
        ("alert", "tone-red", "Late deliveries", pct(scope_late) if scope_late == scope_late else "—", "Region and year only, arrived packages"),
        ("route", "tone-deep", "Repeat customers", pct(repeat_rate) if repeat_rate == repeat_rate else "—", "More than one order in this selection"),
    ]
    cards = "".join(
        f'<div class="kpi {tone}"><span class="kpi-icon"><i class="mark {mark}"></i></span><span>{escape(label)}</span><b>{escape(value)}</b><i>{escape(note)}</i></div>'
        for mark, tone, label, value, note in kpis
    )
    st.markdown(f'<div class="kpis dash-kpis">{cards}</div>', unsafe_allow_html=True)

    st.markdown('<h2 class="section-label"><i class="mark chart"></i>Where the sales are, and where the date fails</h2>', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            card_heading("Sales by region", "Product sales in this selection. Freight is excluded.")
            sales = regions.sort_values("revenue", ascending=False)
            fig = go.Figure(go.Bar(
                x=sales["region"],
                y=sales["revenue"] / 1000,
                marker_color=[REGION_COLORS.get(name, MUTED) for name in sales["region"]],
                text=[money(value) for value in sales["revenue"]],
                textposition="outside",
                hovertemplate="%{x}<br>%{text}<extra></extra>",
            ))
            apply_layout(fig)
            fig.update_layout(showlegend=False, yaxis_title="R$ thousands")
            show(fig)
    with right:
        with st.container(border=True):
            card_heading("Late rate by region", "Arrived packages in this region and year. The dashed line is that selection.")
            rates = regions.dropna(subset=["late_rate"]).sort_values("late_rate", ascending=False)
            if rates.empty:
                st.info("No arrived packages in this region and year.")
            else:
                fig = go.Figure(go.Bar(
                    x=rates["region"],
                    y=rates["late_rate"],
                    marker_color=[DANGER if value > scope_late else OK for value in rates["late_rate"]],
                    text=[f"{pct(value)} · {int(count):,}" for value, count in zip(rates["late_rate"], rates["delivered"])],
                    textposition="outside",
                    hovertemplate="%{x}<br>%{text}<extra></extra>",
                ))
                if scope_late == scope_late:
                    fig.add_hline(y=scope_late, line_dash="dash", line_color=INK)
                apply_layout(fig)
                fig.update_layout(showlegend=False, yaxis_title="Late rate", yaxis_tickformat=".0%", yaxis_range=[0, max(float(rates["late_rate"].max()) * 1.45, 0.2)])
                show(fig)
    with st.container(border=True):
        card_heading("Eight largest states", "Late rate on arrived packages. The label is the rate and the number of deliveries. Red is worse than this region and year.")
        states = (
            scope_delivered.groupby("customer_state", as_index=False)
            .agg(delivered=("order_id", "size"), late_rate=("is_late", "mean"))
            .sort_values("delivered", ascending=False)
            .head(8)
            .sort_values("delivered", ascending=True)
        )
        if states.empty:
            st.info("No arrived packages in this region and year.")
        else:
            fig = go.Figure(go.Bar(
                y=states["customer_state"],
                x=states["late_rate"],
                orientation="h",
                marker_color=[DANGER if value > scope_late else OK for value in states["late_rate"]],
                text=[f"{pct(value)} · {int(count):,}" for value, count in zip(states["late_rate"], states["delivered"])],
                textposition="outside",
                hovertemplate="%{y}<br>%{text}<extra></extra>",
            ))
            if scope_late == scope_late:
                fig.add_vline(x=scope_late, line_dash="dash", line_color=INK)
            apply_layout(fig)
            fig.update_layout(showlegend=False, xaxis_tickformat=".0%", xaxis_title="Late rate", xaxis_range=[0, max(float(states["late_rate"].max()) * 1.55, 0.2)])
            show(fig)

    st.markdown('<h2 class="section-label"><i class="mark clock"></i>How long the trip takes, and what the customer scored</h2>', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            card_heading("Sales on a kept day and a missed day", "Product sales in this selection. No arrival means the package has no delivery date, so it is not called late.")
            promise_rows = [
                ("On time", float(view.loc[view["is_late"] == False, "price"].sum()), int((view["is_late"] == False).sum()), OK),
                ("Late", float(view.loc[view["is_late"] == True, "price"].sum()), int((view["is_late"] == True).sum()), DANGER),
                ("No arrival", float(view.loc[view["is_late"].isna(), "price"].sum()), int(view["is_late"].isna().sum()), MUTED),
            ]
            fig = go.Figure(go.Bar(
                x=[name for name, _, _, _ in promise_rows],
                y=[value / 1000 for _, value, _, _ in promise_rows],
                marker_color=[color for _, _, _, color in promise_rows],
                text=[f"{money(value)} · {count:,}" for _, value, count, _ in promise_rows],
                textposition="outside",
                hovertemplate="%{x}<br>%{text}<extra></extra>",
            ))
            apply_layout(fig)
            fig.update_layout(showlegend=False, yaxis_title="R$ thousands")
            show(fig)
    with right:
        with st.container(border=True):
            card_heading("Sales and orders by year", "Product sales in this selection. The label is sales and the order count.")
            by_year = (
                view.groupby("year", as_index=False)
                .agg(orders=("order_id", "nunique"), revenue=("price", "sum"))
                .sort_values("year")
            )
            fig = go.Figure(go.Bar(
                x=by_year["year"].astype(str),
                y=by_year["revenue"] / 1000,
                marker_color=[ACCENT, ORANGE, OK][: len(by_year)],
                text=[f"{money(value)} · {int(count):,}" for value, count in zip(by_year["revenue"], by_year["orders"])],
                textposition="outside",
                hovertemplate="%{x}<br>%{text}<extra></extra>",
            ))
            apply_layout(fig)
            fig.update_layout(showlegend=False, yaxis_title="R$ thousands")
            show(fig)
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            card_heading("Average trip length by region", "Days from purchase to arrival, for packages that arrived in this region and year.")
            trip = (
                scope_delivered.groupby("region", as_index=False)
                .agg(days=("actual_days", "mean"), delivered=("order_id", "size"))
                .dropna(subset=["days"])
                .sort_values("days", ascending=False)
            )
            if trip.empty:
                st.info("No arrival dates in this region and year.")
            else:
                fig = go.Figure(go.Bar(
                    x=trip["region"],
                    y=trip["days"],
                    marker_color=[REGION_COLORS.get(name, MUTED) for name in trip["region"]],
                    text=[f"{value:.1f} days" for value in trip["days"]],
                    textposition="outside",
                    hovertemplate="%{x}<br>%{text}<br>%{customdata:,} deliveries<extra></extra>",
                    customdata=trip["delivered"],
                ))
                apply_layout(fig)
                fig.update_layout(showlegend=False, yaxis_title="Days")
                show(fig)
    with right:
        with st.container(border=True):
            card_heading("Average stars by region", "Orders with a review in this region and year.")
            star_region = (
                scoped.loc[scoped["review_score"].notna()]
                .groupby("region", as_index=False)
                .agg(score=("review_score", "mean"), reviews=("order_id", "size"))
                .sort_values("score", ascending=True)
            )
            if star_region.empty:
                st.info("No reviews in this region and year.")
            else:
                fig = go.Figure(go.Bar(
                    x=star_region["region"],
                    y=star_region["score"],
                    marker_color=[DANGER if value < 3.5 else WARN if value < 4 else OK for value in star_region["score"]],
                    text=[f"{value:.2f}" for value in star_region["score"]],
                    textposition="outside",
                    hovertemplate="%{x}<br>%{text}<br>%{customdata:,} reviews<extra></extra>",
                    customdata=star_region["reviews"],
                ))
                apply_layout(fig)
                fig.update_layout(showlegend=False, yaxis_title="Average review", yaxis_range=[1, 5.5])
                show(fig)
    with st.container(border=True):
        card_heading("Weak reviews by region", "Share of reviews scored 1 or 2 in this region and year. The dashed line is that selection.")
        scored = scoped.loc[scoped["review_score"].notna()].copy()
        if scored.empty:
            st.info("No reviews in this region and year.")
        else:
            scored["weak"] = scored["review_score"] <= 2
            weak = (
                scored.groupby("region", as_index=False)
                .agg(weak_rate=("weak", "mean"), reviews=("order_id", "size"))
                .sort_values("weak_rate", ascending=False)
            )
            weak_line = float(scored["weak"].mean())
            fig = go.Figure(go.Bar(
                x=weak["region"],
                y=weak["weak_rate"],
                marker_color=[DANGER if value > weak_line else OK for value in weak["weak_rate"]],
                text=[f"{pct(value)} · {int(count):,}" for value, count in zip(weak["weak_rate"], weak["reviews"])],
                textposition="outside",
                hovertemplate="%{x}<br>%{text}<extra></extra>",
            ))
            fig.add_hline(y=weak_line, line_dash="dash", line_color=INK)
            apply_layout(fig)
            fig.update_layout(
                showlegend=False,
                yaxis_title="1- or 2-star reviews",
                yaxis_tickformat=".0%",
                yaxis_range=[0, max(float(weak["weak_rate"].max()) * 1.45, 0.2)],
            )
            show(fig)

    st.markdown('<h2 class="section-label"><i class="mark trend"></i>Whether the miss landed in a busy month</h2>', unsafe_allow_html=True)
    monthly = (
        view.groupby("month", as_index=False)
        .agg(orders=("order_id", "nunique"), revenue=("price", "sum"))
        .sort_values("month")
    )
    if dash_year == "All years":
        monthly = monthly.loc[monthly["month"].between("2017-01", "2018-08")]
    with st.container(border=True):
        card_heading(
            "Sales by month",
            "Product sales in this selection. With all years selected, the chart runs from January 2017 to August 2018, the months with enough orders to read.",
        )
        if monthly.empty:
            st.info("No orders in this month range.")
        else:
            fig = go.Figure(go.Bar(
                x=monthly["month"],
                y=monthly["revenue"] / 1000,
                marker_color=ACCENT,
                text=[money(value) for value in monthly["revenue"]],
                textposition="outside",
                hovertemplate="%{x}<br>%{text}<br>%{customdata:,} orders<extra></extra>",
                customdata=monthly["orders"],
            ))
            apply_layout(fig)
            fig.update_layout(showlegend=False, yaxis_title="R$ thousands")
            show(fig)
    with st.container(border=True):
        card_heading("Late deliveries and weak reviews by month", "Region and year only. A weak review scores 1 or 2. The peak of each line is labeled.")
        month_base = scope_delivered.groupby("month", as_index=False)["is_late"].mean()
        month_neg = scoped.loc[scoped["review_score"].notna()].copy()
        month_neg["is_negative"] = month_neg["review_score"] <= 2
        month_neg = month_neg.groupby("month", as_index=False)["is_negative"].mean()
        trend = month_base.merge(month_neg, on="month", how="inner").sort_values("month")
        if dash_year == "All years":
            trend = trend.loc[trend["month"].between("2017-01", "2018-08")]
        if trend.empty:
            st.info("Not enough months in this region and year.")
        else:
            fig = go.Figure()
            fig.add_scatter(name="Late deliveries", x=trend["month"], y=trend["is_late"], mode="lines", line=dict(color=DANGER, width=2))
            fig.add_scatter(name="Reviews of 1 or 2 stars", x=trend["month"], y=trend["is_negative"], mode="lines", line=dict(color=ACCENT, width=2))
            apply_layout(fig)
            fig.update_yaxes(tickformat=".0%", title="Share of orders")
            show(fig)

    st.markdown('<h2 class="section-label"><i class="mark box"></i>Which products to watch</h2>', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            card_heading("Largest categories by sales", "Item sales in this selection. An order with several products can appear in more than one category.")
            item_rows = commerce["item_rows"]
            cats = (
                item_rows.loc[item_rows["order_id"].isin(view["order_id"])]
                .groupby("category", as_index=False)["price"]
                .sum()
                .sort_values("price", ascending=False)
                .head(8)
                .sort_values("price", ascending=True)
            )
            if cats.empty:
                st.info("No item sales in this selection.")
            else:
                fig = go.Figure(go.Bar(
                    y=cats["category"].map(category_label),
                    x=cats["price"] / 1000,
                    orientation="h",
                    marker_color=ACCENT,
                    text=[money(value) for value in cats["price"]],
                    textposition="outside",
                    hovertemplate="%{y}<br>%{text}<extra></extra>",
                ))
                apply_layout(fig)
                fig.update_layout(showlegend=False, xaxis_title="R$ thousands")
                show(fig)
    with right:
        with st.container(border=True):
            card_heading("Categories that miss the date most often", "Most expensive item on the order. At least 100 arrived orders in this region and year. The dashed line is that selection.")
            typed = scoped.loc[scoped["is_late"].notna() & scoped["category"].notna()]
            focus = (
                typed.groupby("category", as_index=False)
                .agg(delivered_orders=("order_id", "size"), late_rate=("is_late", "mean"), avg_review_score=("review_score", "mean"))
                .loc[lambda rows: rows["delivered_orders"] >= 100]
                .sort_values("late_rate", ascending=False)
                .head(8)
                .sort_values("late_rate", ascending=True)
            )
            if focus.empty:
                st.info("Not enough arrived orders in this region and year to compare product types.")
            else:
                fig = go.Figure(go.Bar(
                    y=focus["category"].map(category_label),
                    x=focus["late_rate"],
                    orientation="h",
                    marker_color=[DANGER if value > scope_late else WARN for value in focus["late_rate"]],
                    text=[f"{pct(value)} · {int(count):,}" for value, count in zip(focus["late_rate"], focus["delivered_orders"])],
                    textposition="outside",
                    customdata=focus["avg_review_score"],
                    hovertemplate="%{y}<br>%{text}<br>Review %{customdata:.2f}<extra></extra>",
                ))
                if scope_late == scope_late:
                    fig.add_vline(x=scope_late, line_dash="dash", line_color=INK)
                apply_layout(fig)
                top = float(focus["late_rate"].max())
                fig.update_layout(showlegend=False, xaxis_tickformat=".0%", xaxis_title="Late rate", xaxis_range=[0, max(top * 1.55, 0.2)])
                show(fig)

    st.markdown('<h2 class="section-label"><i class="mark star"></i>What the customer scored</h2>', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            card_heading("Review scores", "Orders with a review in this selection. A score between two stars is rounded.")
            dist = (
                reviewed["review_score"].round().clip(1, 5).value_counts().sort_index()
                .rename_axis("score").reset_index(name="reviews")
            ) if not reviewed.empty else pd.DataFrame(columns=["score", "reviews"])
            if dist.empty:
                st.info("No reviews in this selection.")
            else:
                star_color = {1: DANGER, 2: ORANGE, 3: WARN, 4: OK, 5: OK}
                fig = go.Figure(go.Bar(
                    x=[str(int(score)) for score in dist["score"]],
                    y=dist["reviews"],
                    marker_color=[star_color.get(int(score), MUTED) for score in dist["score"]],
                    text=[f"{int(value):,}" for value in dist["reviews"]],
                    textposition="outside",
                ))
                apply_layout(fig)
                fig.update_layout(showlegend=False, xaxis_title="Stars", yaxis_title="Reviews")
                show(fig)
    with right:
        with st.container(border=True):
            card_heading("On time against late", "Average stars in this selection. A lower score next to a late package is a pattern, not proof of the cause.")
            compare_x, compare_y, compare_color = [], [], []
            if on_time_score == on_time_score:
                compare_x.append("On time")
                compare_y.append(on_time_score)
                compare_color.append(OK)
            if late_score == late_score:
                compare_x.append("Late")
                compare_y.append(late_score)
                compare_color.append(DANGER)
            fig = go.Figure(go.Bar(
                x=compare_x or ["No reviews"],
                y=compare_y or [0],
                marker_color=compare_color or [MUTED],
                text=[f"{value:.2f}" for value in compare_y] or ["—"],
                textposition="outside",
            ))
            apply_layout(fig)
            fig.update_layout(showlegend=False, yaxis_range=[0, 5.6], yaxis_title="Average review")
            show(fig)

    st.markdown('<h2 class="section-label"><i class="mark file"></i>How the order was paid</h2>', unsafe_allow_html=True)
    pay_rows = commerce["payment_rows"]
    pays = (
        pay_rows.loc[pay_rows["order_id"].isin(view["order_id"]), "payment_type"]
        .value_counts()
        .rename_axis("payment_type")
        .reset_index(name="records")
    )
    pay_late = pay_rows.merge(scope_delivered[["order_id", "is_late"]], on="order_id", how="inner")
    pay_rate = (
        pay_late.groupby("payment_type", as_index=False)
        .agg(records=("order_id", "size"), late_rate=("is_late", "mean"))
        .sort_values("records", ascending=False)
    )
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            card_heading("Payment mix", "Payment records in this selection. Rows marked not defined are omitted.")
            if pays.empty:
                st.info("No payment records for this selection.")
            else:
                labels = [PAYMENT_LABELS.get(name, name) for name in pays["payment_type"]]
                fig = go.Figure(go.Pie(
                    labels=labels,
                    values=pays["records"],
                    hole=0.58,
                    marker=dict(colors=[ACCENT, ORANGE, OK, WARN][: len(labels)]),
                    sort=False,
                ))
                apply_layout(fig)
                fig.update_layout(showlegend=True, legend=dict(orientation="v", y=0.5, yanchor="middle", x=1.02))
                show(fig)
    with right:
        with st.container(border=True):
            card_heading("Late rate by payment method", "Payment records joined to arrived orders in this region and year. An order with two payments is counted twice.")
            if pay_rate.empty:
                st.info("No payment records for arrived orders in this region and year.")
            else:
                names = [PAYMENT_LABELS.get(name, name) for name in pay_rate["payment_type"]]
                fig = go.Figure(go.Bar(
                    x=names,
                    y=pay_rate["late_rate"],
                    marker_color=[DANGER if value > scope_late else ACCENT for value in pay_rate["late_rate"]],
                    text=[pct(value) for value in pay_rate["late_rate"]],
                    textposition="outside",
                    hovertemplate="%{x}<br>%{text}<br>%{customdata:,} records<extra></extra>",
                    customdata=pay_rate["records"],
                ))
                if scope_late == scope_late:
                    fig.add_hline(y=scope_late, line_dash="dash", line_color=INK)
                apply_layout(fig)
                fig.update_layout(
                    showlegend=False,
                    yaxis_title="Late rate",
                    yaxis_tickformat=".0%",
                    yaxis_range=[0, max(float(pay_rate["late_rate"].max()) * 1.45, 0.2)],
                )
                show(fig)
    st.markdown(
        '<p class="foot">Source: Olist public dataset. Revenue is the sum of item price and excludes freight. Late uses the same calendar-date rule as the audit.</p>',
        unsafe_allow_html=True,
    )


def render_overview(summaries: dict, commerce: dict | None) -> None:
    del summaries, commerce
    film = "data:image/webp;base64," + base64.b64encode((ROOT / "assets" / "vd.webp").read_bytes()).decode("ascii")
    st.markdown(
        f"""
        <section class="overview-hero">
          <h1>Delivery Performance</h1>
          <img class="overview-film" src="{film}" alt="Veridi Logistics">
        </section>
        <p class="page-sub">The Last Mile Logistics Auditor examines how accurately Veridi Logistics delivers orders compared with the dates promised to customers. The analysis connects delivery performance with customer review scores to identify where delays occur and whether they are associated with a poorer customer experience.</p>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <section class="callout accent">
          <h2>Business question</h2>
          <p><b>Are delivery performance problems concentrated in specific regions, or are they widespread across the market?</b></p>
        </section>
        <h2 class="section-label"><i class="mark chart"></i>What this analysis measures</h2>
        <div class="guide-grid">
          <section class="home-card">
            <h2><i class="mark check"></i>Delivery performance</h2>
            <p>Measures whether orders arrive on time or later than the estimated delivery date.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark clock"></i>Delivery delay</h2>
            <p>Measures the number of days between the promised delivery date and the actual customer delivery date.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark pin"></i>Regional performance</h2>
            <p>Compares late-delivery rates across customer states to identify geographic differences in delivery performance.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark star"></i>Customer experience</h2>
            <p>Examines whether customers who experience delivery delays tend to give lower review scores.</p>
          </section>
        </div>
        <h2 class="section-label"><i class="mark route"></i>How to read this dashboard</h2>
        <section class="callout accent">
          <ul>
            <li>Monitor overall delivery performance.</li>
            <li>Identify states with higher late-delivery rates.</li>
            <li>Compare on-time and delayed orders.</li>
            <li>Understand the relationship between delivery delays and customer ratings.</li>
            <li>Explore whether certain product categories experience greater delivery challenges.</li>
          </ul>
        </section>
        <h2 class="section-label"><i class="mark file"></i>Data</h2>
        <section class="callout accent">
          <p>This analysis uses the <b>Olist Brazilian E-Commerce Dataset</b>, a real-world e-commerce dataset containing order, customer, product, and customer review information.</p>
        </section>
        <h2 class="section-label"><i class="mark calendar"></i>Delivery status</h2>
        <div class="method-grid">
          <section class="home-card">
            <h2><i class="mark check"></i>On time</h2>
            <p>Delivered on or before the estimated delivery date.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark alert"></i>Late</h2>
            <p>Delivered after the estimated delivery date.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark clock"></i>Super late</h2>
            <p>Delivered more than 5 days after the estimated delivery date.</p>
          </section>
        </div>
        <h2 class="section-label"><i class="mark layers"></i>Analytical approach</h2>
        <ol class="guide-steps">
          <li><b>Orders, customers, reviews, and products</b></li>
          <li><b>Data cleaning and validation</b></li>
          <li><b>Promised versus actual delivery</b></li>
          <li><b>Regional performance</b></li>
          <li><b>Customer sentiment</b></li>
          <li><b>Business insights</b></li>
        </ol>
        <section class="callout accent">
          <h2>Purpose</h2>
          <p>The goal is not only to identify late deliveries, but to understand <b>where delivery performance is weakest and how delivery delays relate to customer experience</b>, providing evidence for further operational investigation.</p>
        </section>
        <h2 class="section-label"><i class="mark route"></i>Where to go next</h2>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="method-grid">
          <section class="home-card">
            <h2><i class="mark chart"></i>Delivery Performance</h2>
            <p>The audit of the promised day. It answers whether the miss is regional or nationwide, and how the review score sits next to a late arrival.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark clock"></i>Dashboard</h2>
            <p>Sales, customers, payments, and the same late-day rule, narrowed by region, year, and whether the package was on time.</p>
          </section>
          <section class="home-card">
            <h2><i class="mark trend"></i>Prediction</h2>
            <p>A check on orders placed in 2018. It uses only the region and the promised lead time, both known on the day the customer orders.</p>
          </section>
        </div>
        """,
        unsafe_allow_html=True,
    )
    open_delivery, open_dashboard, open_predict = st.columns(3)
    open_delivery.button("Open Delivery Performance", key="go_delivery", width="stretch", on_click=choose_section, args=("delivery",))
    open_dashboard.button("Open Dashboard", key="go_dashboard", width="stretch", on_click=choose_section, args=("dashboard",))
    open_predict.button("Open Prediction", key="go_predict", width="stretch", on_click=choose_section, args=("predict",))
    st.markdown(
        """
        <h2 class="section-label"><i class="mark file"></i>Outputs</h2>
        <div class="method-grid">
          <section class="home-card">
            <h2>Notebook</h2>
            <p><a href="https://github.com/danmunyaneza01/AmaliTech-DEG-Project-based-challenges/blob/main/data-engineering/Logistics-auditor/logistics_auditor.ipynb">logistics_auditor.ipynb</a></p>
          </section>
          <section class="home-card">
            <h2>Charts</h2>
            <p><a href="https://htmlpreview.github.io/?https://raw.githubusercontent.com/danmunyaneza01/AmaliTech-DEG-Project-based-challenges/main/data-engineering/Logistics-auditor/logistics_auditor.html">HTML export of the notebook</a></p>
          </section>
          <section class="home-card">
            <h2>Slides</h2>
            <p><a href="https://github.com/danmunyaneza01/AmaliTech-DEG-Project-based-challenges/raw/refs/heads/main/data-engineering/Logistics-auditor/veridi_delivery_audit.pdf">Presentation</a></p>
          </section>
        </div>
        <p class="audit-note">Each section reads the same table of one row per order. The two downloads are at the end of this page.</p>
        """,
        unsafe_allow_html=True,
    )


def render_delivery(summaries: dict, commerce: dict | None) -> None:
    st.markdown(
        """
        <h1 class="page-title"><i class="mark box"></i>Delivery Performance</h1>
        <p class="page-sub">Veridi Logistics Delivery Performance Audit. The promised day, the regions, and the review score.</p>
        """,
        unsafe_allow_html=True,
    )
    render_answer(summaries)
    render_explanation()
    render_audit(summaries, commerce)
    render_actions(summaries)
    render_method()
    render_data_notes()


def render_prediction(risk: dict) -> None:
    st.markdown('<h1 class="page-title"><i class="mark trend"></i>Prediction</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="page-sub">Will this order miss its date? The check uses only the region and the promised lead time, both known when the customer orders.</p>',
        unsafe_allow_html=True,
    )
    kpis = [
        ("file", "2017 orders used to learn", f"{risk['train_orders']:,}", "Delivered orders placed before 2018"),
        ("check", "2018 orders used to check", f"{risk['test_orders']:,}", "January through August 2018"),
        ("clock", "Late rate in the check", pct(risk["test_late_rate"]), "Share of 2018 deliveries that missed"),
        ("alert", "Late rate in the riskiest tenth", pct(risk["precision"]), f"{risk['lift']:.1f} times the overall late rate"),
    ]
    cards = "".join(
        f'<div class="kpi"><i class="mark {mark}"></i><span>{escape(label)}</span><b>{escape(value)}</b><i>{escape(note)}</i></div>'
        for mark, label, value, note in kpis
    )
    st.markdown(f'<div class="kpis">{cards}</div>', unsafe_allow_html=True)

    deciles = risk.get("deciles")
    if deciles is not None and len(deciles):
        st.markdown(
            '<h2 class="section-label"><i class="mark trend"></i>Does a higher score mean a later miss?</h2>',
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            card_heading(
                "2018 orders grouped by the predicted chance of being late",
                "Ten equal groups, from the lowest score to the highest. The bars are what actually happened. The line is the chance the model gave that group. The dashed line is every 2018 delivery.",
            )
            labels = [str(int(value)) for value in deciles["decile"]]
            fig = go.Figure()
            fig.add_bar(
                name="Actual late rate",
                x=labels,
                y=deciles["late_rate"],
                marker_color=DANGER,
                text=[pct(value) for value in deciles["late_rate"]],
                textposition="outside",
            )
            fig.add_scatter(
                name="Average predicted chance",
                x=labels,
                y=deciles["mean_risk"],
                mode="lines+markers",
                line=dict(color=ACCENT, width=2),
            )
            apply_layout(fig)
            fig.add_hline(y=risk["test_late_rate"], line_dash="dash", line_color=INK)
            top = max(float(deciles["late_rate"].max()), float(deciles["mean_risk"].max()), float(risk["test_late_rate"]))
            fig.update_layout(
                yaxis_title="Late rate",
                yaxis_tickformat=".0%",
                yaxis_range=[0, max(top * 1.35, 0.2)],
                xaxis_title="Predicted risk group, lowest to highest",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            )
            show(fig)

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            card_heading("Where the score concentrates the misses", "The riskiest tenth of 2018 orders, compared with every 2018 delivery.")
            fig = go.Figure(go.Bar(
                x=["All 2018 deliveries", "Riskiest tenth"],
                y=[risk["test_late_rate"], risk["precision"]],
                marker_color=[ACCENT, DANGER],
                text=[pct(risk["test_late_rate"]), pct(risk["precision"])],
                textposition="outside",
            ))
            apply_layout(fig)
            fig.update_layout(showlegend=False, yaxis_title="Late rate", yaxis_tickformat=".0%", yaxis_range=[0, max(risk["precision"] * 1.35, 0.2)])
            show(fig)
    with right:
        with st.container(border=True):
            card_heading("What raises the risk", "Odds compared with a Southeast order, at the same promised lead time. Above 1 means more likely to be late.")
            factors = risk["factors"]
            fig = go.Figure(go.Bar(
                y=factors["factor"],
                x=factors["odds"],
                orientation="h",
                marker_color=[DANGER if value >= 1 else OK for value in factors["odds"]],
            ))
            apply_layout(fig)
            fig.add_vline(x=1, line_dash="dash", line_color=INK)
            fig.update_layout(showlegend=False, xaxis_title="Odds versus the reference")
            show(fig)

    factors = risk["factors"]
    northeast = factors.loc[factors["factor"].str.startswith("Northeast"), "odds"]
    northeast_odds = float(northeast.iloc[0]) if len(northeast) else float("nan")
    st.markdown(
        f"""
        <div class="recommend-grid">
          <section class="home-card">
            <h2><i class="mark target"></i>What we are predicting</h2>
            <p>Logistic regression estimates the chance that a delivered order misses the promised day. The only inputs are the customer’s region and the number of days Veridi promised, both known when the order is placed. It does not forecast sales. Seller handling time and the carrier’s road time are unknown that day, so they are not used. Orders placed before 2018 teach the pattern. January through August 2018 is the check, and those orders were not used to fit it.</p>
          </section>
          <section class="home-card finding">
            <h2><i class="mark flag"></i>The outcome</h2>
            <p>On the 2018 check, {pct(risk["test_late_rate"])} of deliveries were late. The riskiest tenth were late {pct(risk["precision"])} of the time, {risk["lift"]:.1f} times the overall rate, and that tenth caught {pct(risk["recall"])} of the late orders. The score separates late from on time only slightly better than remembering each region’s old late rate ({risk["auc"]:.2f} versus {risk["baseline_auc"]:.2f}). At the same promised window, a Northeast order is {northeast_odds:.1f} times as likely to be late as a Southeast order.</p>
          </section>
        </div>
        <p class="foot">The score is a check on this history, not a live promise engine.</p>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    inject_css()
    bind_chart_tools()
    st.session_state.setdefault("section", "overview")
    if st.session_state.section in {"home", "audit"}:
        st.session_state.section = "overview"
    if st.session_state.section not in {"overview", "delivery", "dashboard", "predict"}:
        st.session_state.section = "overview"
    if st.query_params:
        st.query_params.clear()
    render_nav()
    page = st.session_state.section
    summaries = summaries_cached()
    commerce = None
    try:
        commerce = commerce_cached()
    except FileNotFoundError:
        commerce = None

    if page == "dashboard":
        if commerce is None:
            st.markdown(
                '<p class="page-sub">The order-level table is kept out of the public repository. These charts use the summary tables.</p>',
                unsafe_allow_html=True,
            )
            render_delivery(summaries, None)
        else:
            render_dashboard(commerce, summaries)
    elif page == "predict":
        try:
            render_prediction(late_risk_cached())
        except FileNotFoundError as exc:
            st.error(str(exc) or "The Olist CSVs in data/ are required for the prediction.")
    elif page == "delivery":
        render_delivery(summaries, commerce)
    else:
        render_overview(summaries, commerce)
        render_flow()


main()
