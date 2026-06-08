"""
Heavy Equipment Lead Agent — Streamlit Dashboard
Run: streamlit run dashboard/app.py
"""
import sys
import os
import threading
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Heavy Equipment Lead Agent",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state initialization ───────────────────────────────────────────────
if "run_result" not in st.session_state:
    st.session_state.run_result = None
if "running" not in st.session_state:
    st.session_state.running = False
if "progress_log" not in st.session_state:
    st.session_state.progress_log = []
if "progress_pct" not in st.session_state:
    st.session_state.progress_pct = 0


# ── Helpers ────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db_session():
    from src.storage.database import init_db, get_session
    init_db()
    return get_session()


def load_listings(priority=None, status=None, days_back=30):
    from src.storage.database import session_scope, get_all_listings
    from datetime import date, timedelta
    with session_scope() as session:
        date_from = date.today() - timedelta(days=days_back)
        listings = get_all_listings(session, priority=priority, status=status, date_from=date_from)
        return [l.to_dict() for l in listings]


def load_stats():
    from src.storage.database import session_scope, get_run_stats
    with session_scope() as session:
        return get_run_stats(session, date.today())


PRIORITY_COLORS = {
    "high": "#27ae60",
    "medium": "#f39c12",
    "low": "#95a5a6",
    "rejected": "#e74c3c",
}


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/bulldozer.png", width=80)
    st.title("Lead Agent")
    st.markdown("---")

    mode = st.selectbox(
        "Scraper Mode",
        options=["demo", "facebook"],
        index=0,
        help="Demo uses mock data. Facebook requires a logged-in session.",
    )
    os.environ["APP_MODE"] = mode

    st.markdown("---")
    st.subheader("Filters")
    priority_filter = st.multiselect(
        "Priority",
        options=["high", "medium", "low"],
        default=["high", "medium"],
    )
    days_back = st.slider("Show last N days", 1, 90, 30)

    st.markdown("---")
    st.caption(f"Mode: **{mode.upper()}**")
    st.caption(f"DB: `{os.getenv('DATABASE_URL', 'sqlite:///data/leads.db').split('/')[-1]}`")


# ── Main layout ────────────────────────────────────────────────────────────────
st.title("🏗️ Heavy Equipment Lead Agent")
st.caption("Monitor Facebook Marketplace for heavy equipment leads — score, deduplicate, and report.")

tabs = st.tabs(["▶ Run & Overview", "📋 Leads Table", "📊 Analytics", "📄 Reports"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Run & Overview
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    col_run, col_status = st.columns([1, 2])

    with col_run:
        st.subheader("Run Agent")
        run_btn = st.button(
            "▶ Run Now",
            type="primary",
            disabled=st.session_state.running,
            use_container_width=True,
        )

        if st.session_state.running:
            st.warning("⏳ Agent is running...")

    with col_status:
        if st.session_state.run_result:
            res = st.session_state.run_result
            s = res.get("stats", {})
            ts = res.get("today_stats", {})
            st.success("✅ Last run complete")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Found", s.get("total_found", 0))
            m2.metric("New Leads", s.get("new_listings", 0))
            m3.metric("Duplicates", s.get("duplicates_skipped", 0))
            m4.metric("Filtered Out", s.get("filtered_out", 0))

    if run_btn and not st.session_state.running:
        st.session_state.running = True
        st.session_state.progress_log = []
        st.session_state.progress_pct = 0

        progress_bar = st.progress(0)
        status_text = st.empty()
        log_area = st.empty()

        def _progress(msg: str, pct: int):
            st.session_state.progress_log.append(f"[{pct:3d}%] {msg}")
            st.session_state.progress_pct = pct

        try:
            from src.agent.orchestrator import run_sync
            _progress("Starting agent...", 1)
            result = run_sync(progress_callback=_progress)
            st.session_state.run_result = result

            # Update UI after run
            progress_bar.progress(100)
            status_text.success("✅ Run complete!")
            log_area.text("\n".join(st.session_state.progress_log[-15:]))

        except Exception as e:
            st.error(f"Run failed: {e}")
        finally:
            st.session_state.running = False
            st.rerun()

    if st.session_state.progress_log and not st.session_state.running:
        with st.expander("Last run log"):
            st.text("\n".join(st.session_state.progress_log))

    st.markdown("---")
    st.subheader("Today's Summary")
    try:
        stats = load_stats()
        if stats["total"] == 0:
            st.info("No leads found yet for today. Click **Run Now** to start.")
        else:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total Leads", stats["total"])
            c2.metric("🟢 High", stats["high_priority"])
            c3.metric("🟡 Medium", stats["medium_priority"])
            c4.metric("⚪ Low", stats["low_priority"])
            c5.metric("🔴 Rejected", stats["rejected"])

            col_a, col_b = st.columns(2)
            with col_a:
                if stats["by_type"]:
                    fig = px.pie(
                        names=list(stats["by_type"].keys()),
                        values=list(stats["by_type"].values()),
                        title="By Equipment Type",
                        color_discrete_sequence=px.colors.qualitative.Set3,
                    )
                    st.plotly_chart(fig, use_container_width=True)
            with col_b:
                if stats["by_city"]:
                    fig2 = px.bar(
                        x=list(stats["by_city"].values()),
                        y=list(stats["by_city"].keys()),
                        orientation="h",
                        title="Leads by Search City",
                        labels={"x": "Count", "y": "City"},
                        color=list(stats["by_city"].values()),
                        color_continuous_scale="Blues",
                    )
                    st.plotly_chart(fig2, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load stats: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Leads Table
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("All Leads")

    try:
        all_data = []
        for p in (priority_filter if priority_filter else ["high", "medium", "low"]):
            all_data.extend(load_listings(priority=p, days_back=days_back))

        if not all_data:
            st.info("No leads match current filters. Try running the agent first.")
        else:
            df = pd.DataFrame(all_data)

            # Color-coded priority column
            col_search, col_type, col_brand = st.columns(3)
            search_term = col_search.text_input("Search title/location", "")
            type_filter = col_type.multiselect(
                "Equipment Type",
                options=sorted(df["equipment_type"].dropna().unique()),
            )
            brand_options = sorted(df["brand"].dropna().unique())
            brand_filter = col_brand.multiselect("Brand", options=brand_options)

            if search_term:
                mask = (
                    df["listing_title"].str.contains(search_term, case=False, na=False) |
                    df["location_full"].str.contains(search_term, case=False, na=False)
                )
                df = df[mask]
            if type_filter:
                df = df[df["equipment_type"].isin(type_filter)]
            if brand_filter:
                df = df[df["brand"].isin(brand_filter)]

            st.caption(f"Showing {len(df)} leads")

            display_cols = [
                "listing_title", "equipment_type", "brand", "year",
                "price", "location_full", "seller_name", "seller_type",
                "seller_phone", "lead_priority", "lead_score",
                "date_found", "listing_url",
            ]
            existing_cols = [c for c in display_cols if c in df.columns]

            def highlight_priority(row):
                colors = {"high": "background-color: #eafaf1", "medium": "background-color: #fef9e7",
                          "low": "background-color: #f8f9fa", "rejected": "background-color: #fde8e8"}
                color = colors.get(row.get("lead_priority", ""), "")
                return [color] * len(row)

            styled = df[existing_cols].style.apply(highlight_priority, axis=1)
            st.dataframe(styled, use_container_width=True, height=500)

            # Download button
            csv_bytes = df.to_csv(index=False).encode()
            st.download_button(
                "⬇ Download CSV",
                data=csv_bytes,
                file_name=f"leads_{date.today()}.csv",
                mime="text/csv",
            )

    except Exception as e:
        st.error(f"Error loading leads: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Analytics
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Lead Analytics")
    try:
        raw_data = load_listings(days_back=days_back)
        if not raw_data:
            st.info("No data yet — run the agent to populate analytics.")
        else:
            df_all = pd.DataFrame(raw_data)
            df_all = df_all[df_all["lead_priority"].notna()]

            row1_c1, row1_c2 = st.columns(2)

            with row1_c1:
                priority_counts = df_all["lead_priority"].value_counts().reset_index()
                priority_counts.columns = ["Priority", "Count"]
                fig = px.bar(
                    priority_counts, x="Priority", y="Count",
                    color="Priority",
                    color_discrete_map=PRIORITY_COLORS,
                    title="Leads by Priority",
                )
                st.plotly_chart(fig, use_container_width=True)

            with row1_c2:
                if "price" in df_all.columns:
                    df_price = df_all[df_all["price"].notna() & (df_all["lead_priority"] != "rejected")]
                    fig2 = px.histogram(
                        df_price, x="price", color="lead_priority",
                        color_discrete_map=PRIORITY_COLORS,
                        title="Price Distribution",
                        nbins=30,
                        labels={"price": "Price ($)"},
                    )
                    st.plotly_chart(fig2, use_container_width=True)

            row2_c1, row2_c2 = st.columns(2)
            with row2_c1:
                if "brand" in df_all.columns:
                    brand_counts = df_all["brand"].dropna().value_counts().head(10).reset_index()
                    brand_counts.columns = ["Brand", "Count"]
                    fig3 = px.bar(brand_counts, x="Brand", y="Count", title="Top 10 Brands")
                    st.plotly_chart(fig3, use_container_width=True)

            with row2_c2:
                if "equipment_type" in df_all.columns:
                    eq_counts = df_all["equipment_type"].dropna().value_counts().reset_index()
                    eq_counts.columns = ["Type", "Count"]
                    fig4 = px.pie(eq_counts, names="Type", values="Count", title="Equipment Type Mix")
                    st.plotly_chart(fig4, use_container_width=True)

            if "lead_score" in df_all.columns:
                st.subheader("Score Distribution")
                fig5 = px.box(
                    df_all[df_all["lead_score"].notna()],
                    x="lead_priority", y="lead_score",
                    color="lead_priority",
                    color_discrete_map=PRIORITY_COLORS,
                    title="Lead Score by Priority",
                )
                st.plotly_chart(fig5, use_container_width=True)

    except Exception as e:
        st.error(f"Analytics error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Reports
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Generated Reports")

    reports_dir = "data/reports"
    os.makedirs(reports_dir, exist_ok=True)

    html_reports = sorted(
        [f for f in os.listdir(reports_dir) if f.endswith(".html")],
        reverse=True,
    )
    csv_reports = sorted(
        [f for f in os.listdir(reports_dir) if f.endswith(".csv")],
        reverse=True,
    )

    if not html_reports and not csv_reports:
        st.info("No reports generated yet. Run the agent to create the first report.")
    else:
        st.markdown("### HTML Reports")
        for report_file in html_reports[:5]:
            full_path = os.path.join(reports_dir, report_file)
            with open(full_path, "rb") as f:
                st.download_button(
                    f"📄 {report_file}",
                    data=f.read(),
                    file_name=report_file,
                    mime="text/html",
                    key=f"dl_{report_file}",
                )

        if html_reports:
            latest = os.path.join(reports_dir, html_reports[0])
            with open(latest, "r", encoding="utf-8") as f:
                html_content = f.read()
            with st.expander("Preview latest report"):
                st.components.v1.html(html_content, height=600, scrolling=True)

        st.markdown("### CSV Exports")
        for csv_file in csv_reports[:5]:
            full_path = os.path.join(reports_dir, csv_file)
            with open(full_path, "rb") as f:
                st.download_button(
                    f"📊 {csv_file}",
                    data=f.read(),
                    file_name=csv_file,
                    mime="text/csv",
                    key=f"dl_{csv_file}",
                )
