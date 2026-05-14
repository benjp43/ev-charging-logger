import streamlit as st
import pandas as pd
import csv
import os
from datetime import datetime, timedelta

LOG_FILE = "ev_charging_log.csv"

# -----------------------------
# Password protection
# -----------------------------
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.stop()
    elif not st.session_state["password_correct"]:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("Incorrect password")
        st.stop()

check_password()

# -----------------------------
# Helpers
# -----------------------------
def time_to_minutes(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m

def duration_to_hours(d):
    if ":" in d:
        h, m = map(int, d.split(":"))
        return h + m / 60
    return float(d)

def parse_time_input(t):
    try:
        return datetime.strptime(t, "%H:%M").time()
    except:
        st.error("Time must be in HH:MM format")
        st.stop()

def split_cost(start_dt, end_dt, kwh, night_rate, day_rate, night_start, night_end):
    current = start_dt
    night_minutes = 0
    day_minutes = 0

    while current < end_dt:
        next_minute = current + timedelta(minutes=1)
        minute_of_day = current.hour * 60 + current.minute

        if night_start < night_end:
            is_night = night_start <= minute_of_day < night_end
        else:
            is_night = minute_of_day >= night_start or minute_of_day < night_end

        if is_night:
            night_minutes += 1
        else:
            day_minutes += 1

        current = next_minute

    total_minutes = night_minutes + day_minutes
    if total_minutes == 0:
        return 0, 0, 0

    night_kwh = kwh * (night_minutes / total_minutes)
    day_kwh = kwh * (day_minutes / total_minutes)
    cost = night_kwh * night_rate + day_kwh * day_rate

    return cost, night_kwh, day_kwh

def load_csv():
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame(columns=[
            "End Date","Start","End","Duration (h)","kWh",
            "Night kWh","Day kWh","Cost","Off-Peak %"
        ])

    df = pd.read_csv(LOG_FILE, encoding="utf-8-sig")
    df["End Date"] = pd.to_datetime(df["End Date"], dayfirst=True, errors="coerce").dt.date
    return df

def save_csv(df):
    df_to_save = df.copy()
    df_to_save["End Date"] = df_to_save["End Date"].apply(lambda d: d.strftime("%d/%m/%Y"))
    df_to_save.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")

def backfill(df, night_rate, day_rate, night_start, night_end):
    import numpy as np

    if "Night kWh" not in df.columns:
        df["Night kWh"] = np.nan
    if "Day kWh" not in df.columns:
        df["Day kWh"] = np.nan
    if "Cost" not in df.columns:
        df["Cost"] = np.nan
    if "Off-Peak %" not in df.columns:
        df["Off-Peak %"] = pd.Series([None] * len(df), dtype="object")

    for i, row in df.iterrows():
        end_date = row["End Date"]
        if pd.isna(end_date):
            continue

        end_time = datetime.strptime(row["End"], "%H:%M").time()
        end_dt = datetime.combine(end_date, end_time)

        duration_h = float(row["Duration (h)"])
        start_dt = end_dt - timedelta(hours=duration_h)

        kwh = float(row["kWh"])

        cost, night_kwh, day_kwh = split_cost(
            start_dt, end_dt, kwh,
            night_rate, day_rate,
            night_start, night_end
        )

        if night_kwh + day_kwh == 0:
            offpeak = 0
        else:
            offpeak = int((night_kwh / (night_kwh + day_kwh)) * 100)

        df.at[i, "Night kWh"] = round(night_kwh, 2)
        df.at[i, "Day kWh"] = round(day_kwh, 2)
        df.at[i, "Cost"] = round(cost, 2)
        df.at[i, "Off-Peak %"] = f"{offpeak}%"

    return df

# -----------------------------
# Sidebar settings
# -----------------------------
st.sidebar.header("Settings")

night_rate = st.sidebar.number_input("Night rate (£/kWh)", value=0.1497)
day_rate = st.sidebar.number_input("Day rate (£/kWh)", value=0.3371)
night_start = time_to_minutes(st.sidebar.text_input("Night start (HH:MM)", "00:30"))
night_end = time_to_minutes(st.sidebar.text_input("Night end (HH:MM)", "07:30"))

public_rate = st.sidebar.number_input("Public charger rate (£/kWh)", value=0.85)

st.sidebar.write("---")

# -----------------------------
# Bulk Upload Sessions (now in sidebar)
# -----------------------------
st.sidebar.subheader("Bulk Upload Sessions")

bulk_file = st.sidebar.file_uploader("Upload bulk CSV", type=["csv"], key="bulk")

if bulk_file:
    bulk_df = pd.read_csv(bulk_file, encoding="utf-8-sig")
    bulk_df["End Date"] = pd.to_datetime(bulk_df["End Date"], dayfirst=True, errors="coerce").dt.date

    df = pd.concat([df, bulk_df], ignore_index=True)
    df = backfill(df, night_rate, day_rate, night_start, night_end)
    save_csv(df)

    st.sidebar.success("Bulk data uploaded and merged!")

st.sidebar.write("---")

# -----------------------------
# Download CSV (now in sidebar)
# -----------------------------
st.sidebar.subheader("Download CSV")

csv_bytes = df.to_csv(index=False).encode("utf-8-sig")

st.sidebar.download_button(
    label="Download current CSV",
    data=csv_bytes,
    file_name="charging_history.csv",
    mime="text/csv",
    key="sidebar_download"
)

st.sidebar.write("---")

# -----------------------------
# Reset Data (now in sidebar)
# -----------------------------
st.sidebar.subheader("Reset Data")

if st.sidebar.button("Start Fresh / Clear All Data"):
    st.sidebar.warning("This will delete ALL charging data.")

    # Offer backup download
    if len(df) > 0:
        st.sidebar.download_button(
            label="Download backup before deleting",
            data=csv_bytes,
            file_name="charging_history_backup.csv",
            mime="text/csv",
            key="sidebar_backup"
        )

    if st.sidebar.button("Confirm Delete"):
        empty_df = pd.DataFrame(columns=[
            "End Date","Start","End","Duration (h)","kWh",
            "Night kWh","Day kWh","Cost","Off-Peak %"
        ])
        save_csv(empty_df)
        st.sidebar.success("All data cleared.")
        st.experimental_rerun()


# -----------------------------
# Load or create CSV
# -----------------------------
df = load_csv()
df = backfill(df, night_rate, day_rate, night_start, night_end)
save_csv(df)

# -----------------------------
# Bulk Upload Sessions
# -----------------------------
st.header("Bulk Upload Sessions")

bulk_file = st.file_uploader("Upload bulk CSV", type=["csv"], key="bulk")

if bulk_file:
    bulk_df = pd.read_csv(bulk_file, encoding="utf-8-sig")
    bulk_df["End Date"] = pd.to_datetime(bulk_df["End Date"], dayfirst=True, errors="coerce").dt.date

    df = pd.concat([df, bulk_df], ignore_index=True)
    df = backfill(df, night_rate, day_rate, night_start, night_end)
    save_csv(df)

    st.success("Bulk data uploaded, merged, recalculated, and saved!")

# -----------------------------
# Reset / Start Fresh
# -----------------------------
st.header("Reset Data")

if st.button("Start Fresh / Clear All Data"):
    st.warning("This will delete ALL charging data. This cannot be undone.")

    if len(df) > 0:
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="Download current CSV before deleting",
            data=csv_bytes,
            file_name="charging_history_backup.csv",
            mime="text/csv",
            key="backup_download"
        )

    if st.button("Confirm Delete"):
        empty_df = pd.DataFrame(columns=[
            "End Date","Start","End","Duration (h)","kWh",
            "Night kWh","Day kWh","Cost","Off-Peak %"
        ])
        save_csv(empty_df)
        st.success("All data cleared. App reset.")
        st.experimental_rerun()

# -----------------------------
# Main UI
# -----------------------------
st.title("⚡ Ben's EV Charging Logger")

# -----------------------------
# Add Charging Session
# -----------------------------
st.header("Add Charging Session")

mode = st.selectbox(
    "Choose input mode",
    ["Enter start date/time", "Enter end date/time"],
    key="mode_select"
)

col1, col2 = st.columns(2)

if mode == "Enter start date/time":
    start_date = col1.date_input("Start date")
    start_time_str = col2.text_input("Start time (HH:MM)", placeholder="HH:MM")
    start_time = parse_time_input(start_time_str)
    end_date = None
    end_time = None
else:
    end_date = col1.date_input("End date")
    end_time_str = col2.text_input("End time (HH:MM)", placeholder="HH:MM")
    end_time = parse_time_input(end_time_str)
    start_date = None
    start_time = None

duration = st.text_input("Duration (h or HH:MM)", placeholder="e.g. 1.5 or 01:30")
kwh = st.number_input("Energy used (kWh)", min_value=0.0)

if st.button("Add session"):

    if not duration:
        st.error("Please enter a duration.")
        st.stop()

    duration_h = duration_to_hours(duration)

    if mode == "Enter start date/time":
        start_dt = datetime.combine(start_date, start_time)
        end_dt = start_dt + timedelta(hours=duration_h)
    else:
        end_dt = datetime.combine(end_date, end_time)
        start_dt = end_dt - timedelta(hours=duration_h)

    cost, night_kwh, day_kwh = split_cost(
        start_dt, end_dt, kwh,
        night_rate, day_rate,
        night_start, night_end
    )

    if night_kwh + day_kwh == 0:
        offpeak = 0
    else:
        offpeak = int((night_kwh / (night_kwh + day_kwh)) * 100)

    new_row = {
        "End Date": end_dt.date(),
        "Start": start_dt.strftime("%H:%M"),
        "End": end_dt.strftime("%H:%M"),
        "Duration (h)": round(duration_h, 2),
        "kWh": kwh,
        "Night kWh": round(night_kwh, 2),
        "Day kWh": round(day_kwh, 2),
        "Cost": round(cost, 2),
        "Off-Peak %": f"{offpeak}%"
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = backfill(df, night_rate, day_rate, night_start, night_end)
    save_csv(df)
    st.success("Session added!")

# -----------------------------
# Display table
# -----------------------------
st.subheader("Charging History")

df = df.sort_values("End Date").reset_index(drop=True)

df_display = df.copy()
df_display["End Date"] = df_display["End Date"].apply(
    lambda d: d.strftime("%d/%m/%Y") if pd.notna(d) else ""
)
st.dataframe(df_display, use_container_width=True)

# -----------------------------
# Totals + public comparison
# -----------------------------
num_sessions = len(df)

if num_sessions > 0:
    first_date = df["End Date"].iloc[0]
    last_date = df["End Date"].iloc[-1]
else:
    first_date = last_date = None

total_cost = df["Cost"].sum()
total_kwh = df["kWh"].sum()

if num_sessions > 0:
    st.subheader(
        f"Total home charging cost with {num_sessions} sessions "
        f"between {first_date.strftime('%d/%m/%Y')} and {last_date.strftime('%d/%m/%Y')}: £{total_cost:.2f}"
    )
else:
    st.subheader("No charging sessions recorded yet.")

public_cost = total_kwh * public_rate
difference = public_cost - total_cost

st.write(f"At £{public_rate:.2f}/kWh, public charging would cost **£{public_cost:.2f}**")
st.write(f"Difference vs home: **£{difference:.2f}**")

# -----------------------------
# Download CSV
# -----------------------------
st.subheader("Download CSV")

if len(df) > 0:
    start_date_str = df["End Date"].iloc[0].strftime("%d.%m.%Y")
    end_date_str = df["End Date"].iloc[-1].strftime("%d.%m.%Y")
    total_kwh = df["kWh"].sum()

    filename = f"Charging history {start_date_str} to {end_date_str} {total_kwh:.2f}kWh.csv"

    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="Download charging history CSV",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv"
    )
else:
    st.info("No data available to download.")

# -----------------------------
# Custom date range summary
# -----------------------------
st.header("Custom date range summary")

colA, colB = st.columns(2)

start_filter = colA.date_input("Start of range (End Date)", key="range_start")
end_filter = colB.date_input("End of range (End Date)", key="range_end")

df = df.sort_values("End Date").reset_index(drop=True)

mask = (df["End Date"] >= start_filter) & (df["End Date"] <= end_filter)
filtered_df = df[mask].copy()

st.subheader("Filtered Sessions")

filtered_display = filtered_df.copy()
filtered_display["End Date"] = filtered_display["End Date"].apply(
    lambda d: d.strftime("%d/%m/%Y") if pd.notna(d) else ""
)
st.dataframe(filtered_display, use_container_width=True)

total_cost_range = filtered_df["Cost"].sum()

st.subheader("Summary")
st.write(
    f"**Total cost from {start_filter.strftime('%d/%m/%Y')} "
    f"to {end_filter.strftime('%d/%m/%Y')}: £{total_cost_range:.2f}**"
)
