-- Hour of the (local) day. Facts join on the local hour so "5pm peak" means 5pm in the region.

with hours as (
    select row_number() over (order by seq4()) - 1 as hour_key
    from table(generator(rowcount => 24))
)

select
    hour_key,
    lpad(hour_key::varchar, 2, '0') || ':00' as hour_label,
    case
        when hour_key between 0 and 5 then 'Overnight'
        when hour_key between 6 and 11 then 'Morning'
        when hour_key between 12 and 17 then 'Afternoon'
        else 'Evening'
    end as day_part,
    -- Standard 16-hour on-peak block (hour-ending 07..22).
    hour_key between 7 and 22 as is_on_peak
from hours
