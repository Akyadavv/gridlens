{% docs __overview__ %}
# GridLens

Analytics platform on public US power-grid data.

**Sources**: EIA API v2 (hourly demand, day-ahead demand forecast, generation by fuel;
EIA-860M plant inventory) and Open-Meteo (hourly weather for each region's main city).

**Layers**

| Layer | Materialization | Purpose |
|---|---|---|
| `staging` | views | One model per source table: typed columns, latest-load-wins de-duplication |
| `intermediate` | views | Weather source preference, plant rollup feeding the SCD2 snapshot |
| `marts.core` | tables / incremental | Kimball star: `fct_hourly_demand`, `fct_generation_by_fuel`, `fct_weather_hourly` + conformed dims |
| `marts.forecast` | tables | Feature table for the forecast job, forecasts vs actuals, daily accuracy vs EIA |

All timestamps are stored in UTC (`period_utc`); `period_local`, `date_key` and `hour_key`
are derived per region from `dim_region.timezone`.
{% enddocs %}
