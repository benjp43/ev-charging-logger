import streamlit as st
from datetime import datetime, date, time, timedelta
import pandas as pd

st.set_page_config(page_title="EV Charging Cost Calculator", layout="centered")

st.title("EV Charging Cost Calculator")

st.markdown(
    "Use this as a **calculator**. After each session, copy the results into your "
    "spreadsheet to share with your parents."
)

# --- INPUTS ---

st.subheader("Session details")

mode = st.radio(
    "Input mode",
    ["Start + Duration", "End + Duration"],
    horizontal=True,
)

col1, col2 = st.columns(2)
with col1:
    kwh = st.number_input("Energy used (kWh)", min_value=0.0, step=0.1)

with col2:
    duration_input = st.time_input("Duration (HH:MM)", value=time(1, 0))

# Convert HH:MM → decimal hours
duration_hours = duration_input.hour + duration_input.minute / 60


col3, col4 = st.columns(2)
if mode == "Start + Duration":
    with col3:
        start_date = st.date_input("Start date", value=date.today())
    with col4:
        start_time = st.time_input("Start time", value=time(13, 30))
    end_date = None
    end_time = None
else:
    with col3:
        end_date = st.date_input("End date", value=date.today())
    with col4:
        end_time = st.time_input("End time", value=time(7, 30))
    start_date = None
    start_time = None


st.subheader("Tariff settings")

col5, col6 = st.columns(2)
with col5:
    night_start_time = st.time_input("Night rate starts at", value=time(0, 30))
with col6:
    night_end_time = st.time_input("Night rate ends at", value=time(7, 30))

col7, col8 = st.columns(2)
with col7:
    night_rate = st.number_input(
        "Night rate (per kWh)", min_value=0.0, value=0.1497, step=0.001
    )
with col8:
    day_rate = st.number_input(
        "Day rate (per kWh)", min_value=0.0, value=0.3371, step=0.001
    )


def compute_start_end(mode, start_date, start_time, end_date, end_time, duration_hours):
    if duration_hours <= 0:
        return None, None

    duration = timedelta(hours=duration_hours)

    if mode == "Start + Duration":
        start_dt = datetime.combine(start_date, start_time)
        end_dt = start_dt + duration
    else:
        end_dt = datetime.combine(end_date, end_time)
        start_dt = end_dt - duration

    return start_dt, end_dt


def split_session_by_day(start_dt, end_dt, night_start_time, night_end_time):
    """
    Split a charging session into daily segments and compute
    night/day minutes for each day.
    """
    results = []
    total_night_minutes = 0.0
    total_day_minutes = 0.0

    current = start_dt

    while current < end_dt:
        # End of this day (midnight of next day)
        day_end = datetime.combine(current.date() + timedelta(days=1), time(0, 0))
        seg_end = min(end_dt, day_end)

        seg_start = current
        seg_minutes = (seg_end - seg_start).total_seconds() / 60.0

        # Night window for this day
        night_start_dt = datetime.combine(seg_start.date(), night_start_time)
        night_end_dt = datetime.combine(seg_start.date(), night_end_time)
        if night_end_dt <= night_start_dt:
            night_end_dt += timedelta(days=1)

        # Overlap between [seg_start, seg_end] and [night_start_dt, night_end_dt]
        overlap_start = max(seg_start, night_start_dt)
        overlap_end = min(seg_end, night_end_dt)
        night_minutes = max(
            0.0, (overlap_end - overlap_start).total_seconds() / 60.0
        )

        # Clamp for safety
        night_minutes = max(0.0, min(night_minutes, seg_minutes))
        day_minutes = seg_minutes - night_minutes

        total_night_minutes += night_minutes
        total_day_minutes += day_minutes

        results.append(
            {
                "Day": seg_start.date().isoformat(),
                "Segment start": seg_start.strftime("%Y-%m-%d %H:%M"),
                "Segment end": seg_end.strftime("%Y-%m-%d %H:%M"),
                "Total minutes": round(seg_minutes, 1),
                "Night minutes": round(night_minutes, 1),
                "Day minutes": round(day_minutes, 1),
            }
        )

        current = seg_end

    return results, total_night_minutes, total_day_minutes


st.markdown("---")

if st.button("Calculate"):

    if kwh <= 0 or duration_hours <= 0:
        st.error("Please enter a positive kWh and duration.")
    else:
        start_dt, end_dt = compute_start_end(
            mode, start_date, start_time, end_date, end_time, duration_hours
        )

        if start_dt is None or end_dt is None or start_dt >= end_dt:
            st.error("Check your dates/times and duration — start must be before end.")
        else:
            per_day, night_minutes, day_minutes = split_session_by_day(
                start_dt, end_dt, night_start_time, night_end_time
            )

            total_minutes = night_minutes + day_minutes

            if total_minutes <= 0:
                st.error("Something went wrong: total minutes is zero.")
            else:
                night_kwh = kwh * (night_minutes / total_minutes)
                day_kwh = kwh - night_kwh

                night_cost = night_kwh * night_rate
                day_cost = day_kwh * day_rate
                total_cost = night_cost + day_cost

                offpeak_pct = night_kwh / kwh if kwh > 0 else 0.0

                st.subheader("Per‑day breakdown")
                df = pd.DataFrame(per_day)
                st.dataframe(df, use_container_width=True)

                st.subheader("Summary")

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**Start:** {start_dt.strftime('%Y-%m-%d %H:%M')}")
                    st.markdown(f"**End:** {end_dt.strftime('%Y-%m-%d %H:%M')}")
                    st.markdown(f"**Duration:** {duration_input.strftime('%H:%M')}")
                    st.markdown(f"**Total kWh:** {kwh:.2f}")
                with col_b:
                    st.markdown(f"**Night kWh:** {night_kwh:.2f}")
                    st.markdown(f"**Day kWh:** {day_kwh:.2f}")
                    st.markdown(f"**Night cost:** £{night_cost:.2f}")
                    st.markdown(f"**Day cost:** £{day_cost:.2f}")
                    st.markdown(f"**Total cost:** £{total_cost:.2f}")
                    st.markdown(f"**Off‑peak %:** {offpeak_pct*100:.1f}%")

                st.info(
                    "Copy **Night kWh, Day kWh, Total cost, Off‑peak %** into your "
                    "spreadsheet log to share with your parents."
                )
