-- Conformed region dimension shared by every fact (demand, generation, weather, forecasts).

select
    {{ dbt_utils.generate_surrogate_key(['region_code']) }} as region_key,
    region_code,
    region_name,
    iso_type,
    timezone,
    weather_city,
    latitude,
    longitude
from {{ ref('regions') }}
