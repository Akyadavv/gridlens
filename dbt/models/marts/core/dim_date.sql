with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="'" ~ var('calendar_start') ~ "'::date",
        end_date="'" ~ var('calendar_end') ~ "'::date"
    ) }}
),

days as (
    select date_day::date as date_day from spine
),

holidays as (
    select
        holiday_date,
        holiday_name
    from {{ ref('us_holidays') }}
)

select
    {{ date_key('d.date_day') }} as date_key,
    d.date_day,
    year(d.date_day) as year_number,
    quarter(d.date_day) as quarter_number,
    month(d.date_day) as month_number,
    monthname(d.date_day) as month_name,
    day(d.date_day) as day_of_month,
    dayofyear(d.date_day) as day_of_year,
    weekiso(d.date_day) as iso_week,
    dayofweekiso(d.date_day) as day_of_week_iso,
    dayname(d.date_day) as day_name,
    dayofweekiso(d.date_day) in (6, 7) as is_weekend,
    h.holiday_date is not null as is_holiday,
    h.holiday_name,
    dayofweekiso(d.date_day) not in (6, 7) and h.holiday_date is null as is_business_day,
    case
        when month(d.date_day) in (12, 1, 2) then 'Winter'
        when month(d.date_day) in (3, 4, 5) then 'Spring'
        when month(d.date_day) in (6, 7, 8) then 'Summer'
        else 'Autumn'
    end as season
from days as d
left join holidays as h
    on d.date_day = h.holiday_date
