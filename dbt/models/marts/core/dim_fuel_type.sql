select
    {{ dbt_utils.generate_surrogate_key(['fuel_type_code']) }} as fuel_type_key,
    fuel_type_code,
    fuel_type_name,
    fuel_category,
    is_renewable,
    is_dispatchable,
    display_order
from {{ ref('fuel_types') }}
