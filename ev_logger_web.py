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
    duration_str = st.text_input("Duration (HH:MM)", value="01:00")

# Parse duration HH:MM → decimal hours
try:
    dh, dm = duration_str.split(":")
    duration_hours = int(dh) + int(dm) / 60
except:
    duration_hours = 0
    st.error("Enter duration as HH:MM, e.g. 12:52")

col3, col4 = st.columns(2)

if mode == "Start + Duration":
    with col3:
        start_date = st.date_input("Start date", value=date.today())
    with col4:
        start_time_str = st.text_input("Start time (HH:MM)", value="13:30")

    # Parse start time
    try:
        sh, sm = start_time_str.split(":")
        start_time = time(int(sh), int(sm))
    except:
        start_time = None
        st.error("Enter start time as HH:MM")

    end_date = None
    end_time = None

else:
    with col3:
        end_date = st.date_input("End date", value=date.today())
    with col4:
        end_time_str = st.text_input("End time (HH:MM)", value="07:30")

    # Parse end time
    try:
        eh, em = end_time_str.split(":")
        end_time = time(int(eh), int(em))
    except:
        end_time = None
        st.error("Enter end time as HH:MM")

    start_date = None
    start_time = None


st.subheader("Tariff settings")

col5, col6 = st.columns(2)
with col5:
    night_start_str = st.text_input("Night rate starts at (HH:MM)", value="00:30")
with col6:
    night_end_str = st.text_input("Night rate ends at (HH:MM)", value="07:30")

# Parse night window
try:
    nsh, nsm = night_start_str.split(":")
    night_start_time = time(int(nsh), int(nsm))
    neh, nem = night_end_str.split(":")
    night_end_time = time(int(neh), int(nem))
except:
    night_start_time = time(0, 30)
    night_end_time = time(7, 30)
    st.error("Enter night window times as HH:MM")

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
        if start_time is None:
            return None, None
        start_dt = datetime.combine(start_date, start_time)
        end_dt = start_dt + duration
    else:
        if end_time is None:
            return None, None
        end_dt = datetime.combine(end_date, end_time)
        start_dt = end_dt - duration

    return start_dt, end_dt


def split_session_by_day(start_dt, end_dt, night_start_time, night_end_time):
    results = []
    total_night_minutes = 0.0
    total_day_minutes = 0.0

    current = start_dt

    while current < end_dt:
        day_end = datetime.combine(current.date() + timedelta(days=1), time(0, 0))
        seg_end = min(end_dt, day_end)

        seg_start = current
        seg_minutes = (seg_end - seg_start).total_seconds() / 60.0

        night_start_dt = datetime.combine(seg_start.date(), night_start_time)
        night_end_dt = datetime.combine(seg_start.date(), night_end_time)
        if night_end_dt <= night_start_dt:
            night_end_dt += timedelta(days=1)

        overlap_start = max(seg_start, night_start_dt)
        overlap_end = min(seg_end, night_end_dt)
        night_minutes = max(
            0.0, (overlap_end - overlap_start).total_seconds() / 60.0
        )

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
                    st.markdown(f"**Duration:** {duration_str}")
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
