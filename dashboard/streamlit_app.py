"""GridLens dashboard: demand vs forecast, generation mix, forecast error over time.

Runs in Streamlit in Snowflake (uses the app owner's session) or locally:
    pip install -e ".[dashboard]" && streamlit run dashboard/streamlit_app.py
(locally it connects with the same key-pair env vars as the rest of the project).
"""

from __future__ import annotations

import os

import altair as alt
import pandas as pd
import streamlit as st

MARTS = os.getenv("GRIDLENS_MARTS", "ANALYTICS.MARTS")

# Validated categorical palette (fixed order, light / dark steps). Color follows the entity:
# a model or fuel category keeps its color no matter what the filters show.
PALETTE = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"],
    "dark": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"],
}
DEMAND_SERIES = ["Actual demand", "GridLens (LightGBM)", "EIA day-ahead"]
MODEL_SERIES = ["lightgbm", "eia_day_ahead", "sarima", "seasonal_naive"]
MODEL_LABELS = {
    "lightgbm": "GridLens LightGBM",
    "eia_day_ahead": "EIA day-ahead",
    "sarima": "SARIMA",
    "seasonal_naive": "Seasonal naive",
}
FUEL_CATEGORIES = ["Fossil", "Nuclear", "Renewable", "Storage", "Other"]


# ---- Data access -------------------------------------------------------------------------

@st.cache_resource
def _session():
    try:
        from snowflake.snowpark.context import get_active_session

        return ("snowpark", get_active_session())
    except Exception:
        from gridlens.common.snowflake import get_connection

        return ("connector", get_connection(role=os.getenv("SNOWFLAKE_ROLE", "REPORTER")))


@st.cache_data(ttl=600, show_spinner=False)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    kind, conn = _session()
    if kind == "snowpark":
        df = conn.sql(sql, params=list(params)).to_pandas()
    else:
        cur = conn.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def _show(chart) -> None:
    # Newer Streamlit takes width="stretch"; Streamlit in Snowflake may run an older release.
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def _mode() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


def _surface() -> str:
    """Gap color between stacked segments: the page background in either theme."""
    return "#0e1117" if _mode() == "dark" else "#ffffff"


def _scale(domain: list[str], labels: dict[str, str] | None = None) -> alt.Scale:
    colors = PALETTE[_mode()][: len(domain)]
    return alt.Scale(domain=[labels.get(d, d) for d in domain] if labels else domain, range=colors)


def _end_labels(df: pd.DataFrame, x: str, y: str, series: str, scale: alt.Scale) -> alt.Chart:
    """Direct labels at the last point of each line, in text ink with a colored dot beside."""
    last = df.sort_values(x).groupby(series, as_index=False).last()
    base = alt.Chart(last).encode(x=f"{x}:T", y=f"{y}:Q")
    dot = base.mark_circle(size=64).encode(color=alt.Color(f"{series}:N", scale=scale, legend=None))
    text = base.mark_text(align="left", dx=8, fontSize=11).encode(text=f"{series}:N")
    return dot + text


def _crosshair_line(df: pd.DataFrame, x: str, y: str, series: str, scale: alt.Scale,
                    y_title: str, tooltip: list, value_format: str = ",.1f",
                    end_labels: bool = True, zero: bool = True) -> alt.LayerChart:
    """Lines + a vertical crosshair whose tooltip lists every series at the hovered time."""
    hover = alt.selection_point(fields=[x], nearest=True, on="pointerover", empty=False)
    base = alt.Chart(df).encode(x=alt.X(f"{x}:T", title=None, axis=alt.Axis(grid=False)))
    lines = base.mark_line(strokeWidth=2).encode(
        y=alt.Y(f"{y}:Q", title=y_title, scale=alt.Scale(zero=zero),
                axis=alt.Axis(grid=True, gridOpacity=0.3)),
        color=alt.Color(f"{series}:N", scale=scale, legend=alt.Legend(orient="top", title=None)),
    )
    names = [n for n in scale.domain if n in set(df[series])]
    rule = (
        base.transform_pivot(series, value=y, groupby=[x])
        .mark_rule(strokeWidth=1)
        .encode(
            opacity=alt.condition(hover, alt.value(0.5), alt.value(0)),
            tooltip=tooltip + [alt.Tooltip(f"{n}:Q", format=value_format) for n in names],
        )
        .add_params(hover)
    )
    points = lines.mark_point(size=60, filled=True).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0))
    )
    layers = [lines, points, rule]
    if end_labels:  # only where lines end apart; converging lines would make labels collide
        layers.append(_end_labels(df, x, y, series, scale))
    return alt.layer(*layers)


# ---- Page -------------------------------------------------------------------------------

st.set_page_config(page_title="GridLens", layout="wide")
st.title("GridLens")
st.caption("US grid demand, generation mix and day-ahead forecast accuracy - EIA + Open-Meteo data")

regions = query(f"select region_code, region_name, timezone from {MARTS}.DIM_REGION order by region_code")
f1, f2, _ = st.columns([2, 2, 3])
region = f1.selectbox(
    "Region", regions["region_code"],
    format_func=lambda c: f"{c} - {regions.set_index('region_code').at[c, 'region_name']}",
)
days = f2.select_slider("Window", options=[7, 14, 30, 90], value=14, format_func=lambda d: f"Last {d} days")

# ---- KPI row ------------------------------------------------------------------------------

acc = query(
    f"""select model_name, sum(mape_pct * n_hours) / nullif(sum(n_hours), 0) as mape_pct
    from {MARTS}.FCT_FORECAST_ACCURACY_DAILY
    where region_code = ? and date_key >= to_number(to_char(dateadd(day, -?, current_date), 'YYYYMMDD'))
    group by 1""",
    (region, days),
).set_index("model_name")["mape_pct"]

peak = query(
    f"""select max(demand_mwh) as peak_mwh from {MARTS}.FCT_HOURLY_DEMAND
    where region_code = ? and period_utc >= dateadd(day, -?, current_date)""",
    (region, days),
)["peak_mwh"].iloc[0]

k1, k2, k3 = st.columns(3)
gl, eia = acc.get("lightgbm"), acc.get("eia_day_ahead")
k1.metric("GridLens MAPE", f"{gl:.2f}%" if pd.notna(gl) else "n/a",
          delta=f"{gl - eia:+.2f} pts vs EIA" if pd.notna(gl) and pd.notna(eia) else None,
          delta_color="inverse")
k2.metric("EIA day-ahead MAPE", f"{eia:.2f}%" if pd.notna(eia) else "n/a")
k3.metric("Peak demand", f"{peak / 1000:,.1f} GW" if pd.notna(peak) else "n/a")

# ---- 1. Demand vs forecast ------------------------------------------------------------------

st.subheader("Demand vs forecast")
demand = query(
    f"""select d.period_local, d.demand_mwh, d.eia_day_ahead_forecast_mwh, f.forecast_mwh as gridlens_mwh
    from {MARTS}.FCT_HOURLY_DEMAND d
    left join {MARTS}.FCT_DEMAND_FORECAST f
      on f.region_code = d.region_code and f.period_utc = d.period_utc and f.model_name = 'lightgbm'
    where d.region_code = ? and d.period_utc >= dateadd(day, -?, current_date)
    qualify row_number() over (partition by d.period_utc order by f.is_backtest) = 1
    union all
    -- tomorrow: the live forecast has no actuals yet
    select f.period_local, null, null, f.forecast_mwh
    from {MARTS}.FCT_DEMAND_FORECAST f
    where f.region_code = ? and f.model_name = 'lightgbm' and not f.is_backtest
      and f.actual_demand_mwh is null and f.period_utc >= current_date""",
    (region, days, region),
)
if demand.empty:
    st.info("No demand data for this region yet.")
else:
    long = demand.rename(columns={
        "demand_mwh": DEMAND_SERIES[0], "gridlens_mwh": DEMAND_SERIES[1],
        "eia_day_ahead_forecast_mwh": DEMAND_SERIES[2],
    }).melt("period_local", var_name="series", value_name="mwh").dropna()
    long["gw"] = long["mwh"] / 1000
    _show(
        _crosshair_line(
            long, "period_local", "gw", "series", _scale(DEMAND_SERIES), "GW (hourly average)",
            tooltip=[alt.Tooltip("period_local:T", title="Local time", format="%a %d %b %H:00")],
            end_labels=False, zero=False,
        ).properties(height=320),
    )

# ---- 2. Generation mix ----------------------------------------------------------------------

st.subheader("Generation mix by fuel")
mix = query(
    f"""select date_trunc('day', g.period_local) as day, t.fuel_category,
           sum(g.net_generation_mwh) / 1000 as gwh
    from {MARTS}.FCT_GENERATION_BY_FUEL g
    join {MARTS}.DIM_FUEL_TYPE t on t.fuel_type_key = g.fuel_type_key
    where g.region_code = ? and g.period_utc >= dateadd(day, -?, current_date)
    group by 1, 2""",
    (region, days),
)
if mix.empty:
    st.info("No generation data for this region yet.")
else:
    mix["order"] = mix["fuel_category"].map({c: i for i, c in enumerate(FUEL_CATEGORIES)})
    bars = alt.Chart(mix).mark_bar(stroke=_surface(), strokeWidth=1).encode(
        x=alt.X("yearmonthdate(day):O", title=None, axis=alt.Axis(format="%a %d %b", labelAngle=0)),
        y=alt.Y("sum(gwh):Q", title="GWh per day", stack="zero"),
        color=alt.Color("fuel_category:N", scale=_scale(FUEL_CATEGORIES),
                        legend=alt.Legend(orient="top", title=None)),
        order=alt.Order("order:Q"),
        tooltip=[
            alt.Tooltip("day:T", format="%a %d %b"),
            alt.Tooltip("fuel_category:N", title="Fuel"),
            alt.Tooltip("sum(gwh):Q", title="GWh", format=",.1f"),
        ],
    )
    _show(bars.properties(height=300))

# ---- 3. Forecast error over time ------------------------------------------------------------

st.subheader("Forecast error over time (daily MAPE)")
err = query(
    f"""select to_date(date_key::varchar, 'YYYYMMDD') as day, model_name, mape_pct, n_hours
    from {MARTS}.FCT_FORECAST_ACCURACY_DAILY
    where region_code = ? and date_key >= to_number(to_char(dateadd(day, -?, current_date), 'YYYYMMDD'))""",
    (region, days),
)
if err.empty:
    st.info("No scored forecasts yet - they appear after the first forecast run has actuals.")
else:
    err["day"] = pd.to_datetime(err["day"])  # Snowflake DATE arrives as python date objects
    err["model"] = err["model_name"].map(MODEL_LABELS).fillna(err["model_name"])
    _show(
        _crosshair_line(
            err, "day", "mape_pct", "model", _scale(MODEL_SERIES, MODEL_LABELS), "MAPE (%)",
            tooltip=[alt.Tooltip("day:T", format="%a %d %b")],
        ).properties(height=300),
    )
    with st.expander("Table view"):
        st.dataframe(
            err.pivot_table(index="day", columns="model", values="mape_pct").round(2).sort_index(ascending=False)
        )

st.caption(
    "MAPE = mean absolute percentage error over the hours scored. Backtest days use observed "
    "weather (an upper bound on skill); live forecasts use forecast weather."
)
