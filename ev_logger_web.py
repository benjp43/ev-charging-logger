import streamlit as st
import pandas as pd
import csv
import os
from datetime import datetime, timedelta

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


LOG_FILE = "ev_charging_log.csv"

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

# -----------------------------
# Load CSV
# -----------------------------
def load_csv():
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame(columns=[
            "End Date","Start","End","Duration (h)","kWh",
            "Night kWh","Day kWh","Cost","Off-Peak %"
        ])

    df = pd.read_csv(LOG_FILE, encoding="utf-8-sig")

    # Convert End Date to datetime (handles strings)
    df["End Date"] = pd.to_datetime(df["End Date"], dayfirst=True, errors="coerce")

    # Convert to pure date (drops time)
    df["End Date"] = df["End Date"].dt.date

    return df

# -----------------------------
# Save CSV
# -----------------------------
def save_csv(df):
    df_to_save = df.copy()
    df_to_save["End Date"] = df_to_save["End Date"].dt.strftime("%d/%m/%Y")
    df_to_save.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")

# -----------------------------
# Backfill missing columns
# -----------------------------
def backfill(df, night_rate, day_rate, night_start, night_end):

    import numpy as np

    # Ensure calculated columns exist with correct dtypes
    if "Night kWh" not in df.columns:
        df["Night kWh"] = np.nan
    if "Day kWh" not in df.columns:
        df["Day kWh"] = np.nan
    if "Cost" not in df.columns:
        df["Cost"] = np.nan
    if "Off-Peak %" not in df.columns:
        df["Off-Peak %"] = pd.Series([None] * len(df), dtype="object")

    # Recalculate ALL rows
    for i, row in df.iterrows():

        end_date = row["End Date"]  # already a date
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

        offpeak = int((night_kwh / (night_kwh + day_kwh)) * 100)

        df.at[i, "Night kWh"] = round(night_kwh, 2)
        df.at[i, "Day kWh"] = round(day_kwh, 2)
        df.at[i, "Cost"] = round(cost, 2)
        df.at[i, "Off-Peak %"] = f"{offpeak}%"

    return df

# -----------------------------
# Streamlit UI
# -----------------------------
st.title("⚡ Ben's EV Charging Logger")

st.sidebar.header("Settings")

night_rate = st.sidebar.number_input("Night rate (£/kWh)", value=0.1497)
day_rate = st.sidebar.number_input("Day rate (£/kWh)", value=0.3371)
night_start = time_to_minutes(st.sidebar.text_input("Night start (HH:MM)", "00:30"))
night_end = time_to_minutes(st.sidebar.text_input("Night end (HH:MM)", "07:30"))

public_rate = st.sidebar.number_input("Public charger rate (£/kWh)", value=0.85)

st.sidebar.write("---")

# -----------------------------
# Load and backfill CSV
# -----------------------------
df = load_csv()
df = backfill(df, night_rate, day_rate, night_start, night_end)
save_csv(df)

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

# -----------------------------
# TIME SPINNER WIDGET
# -----------------------------
def time_spinner(label_prefix, container):
    col_h, col_m = container.columns([1, 1])

    hour = col_h.number_input(f"{label_prefix} hour", min_value=0, max_value=23, step=1, value=0)
    minute = col_m.number_input(f"{label_prefix} minute", min_value=0, max_value=59, step=1, value=0)

    return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()

# -----------------------------
# MODE: Start or End
# -----------------------------
if mode == "Enter start date/time":
    start_date = col1.date_input("Start date")
    start_time = time_spinner("Start", col2)
    end_date = None
    end_time = None
else:
    end_date = col1.date_input("End date")
    end_time = time_spinner("End", col2)
    start_date = None
    start_time = None

# -----------------------------
# Duration + kWh
# -----------------------------
duration = st.text_input("Duration (h or HH:MM)", placeholder="e.g. 1.5 or 01:30")
kwh = st.number_input("Energy used (kWh)", min_value=0.0)

# -----------------------------
# Add Session Button
# -----------------------------
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
    save_csv(df)
    st.success("Session added!")

# -----------------------------
# Display table
# -----------------------------

st.subheader("Charging History")

# Convert End Date to datetime for sorting
df["EndDate_dt"] = pd.to_datetime(df["End Date"], format="%d/%m/%Y")

# Sort oldest → newest
df = df.sort_values("EndDate_dt").reset_index(drop=True)

# Remove helper column
df = df.drop(columns=["EndDate_dt"])

# Show table
st.dataframe(df, use_container_width=True)

# -----------------------------
# Totals + public comparison
# -----------------------------

# Compute session count and date range
num_sessions = len(df)

if num_sessions > 0:
    first_date = df["End Date"].iloc[0]
    last_date = df["End Date"].iloc[-1]

total_cost = df["Cost"].sum()
total_kwh = df["kWh"].sum()

if num_sessions > 0:
    st.subheader(
        f"Total home charging cost with {num_sessions} sessions "
        f"between {first_date} and {last_date}: £{total_cost:.2f}"
    )
else:
    st.subheader("No charging sessions recorded yet.")
public_cost = total_kwh * public_rate
difference = public_cost - total_cost

st.write(f"At £{public_rate:.2f}/kWh, public charging would cost **£{public_cost:.2f}**")
st.write(f"Difference vs home: **£{difference:.2f}**")

st.subheader("Download CSV")

if len(df) > 0:
    start_date = df["End Date"].iloc[0].replace("/", ".")
    end_date = df["End Date"].iloc[-1].replace("/", ".")
    total_kwh = df["kWh"].sum()

    filename = f"Charging history {start_date} to {end_date} {total_kwh:.2f}kWh.csv"

    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="Download charging history CSV",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv"
    )
else:
    st.info("No data available to download.")

# Compute summary info
num_sessions = len(df)

if num_sessions > 0:
    first_date = df["End Date"].iloc[0]
    last_date = df["End Date"].iloc[-1]
else:
    first_date = last_date = None

total_cost = df["Cost"].sum()

# -----------------------------
# Custom date range summary
# -----------------------------
st.header("Custom date range summary")

colA, colB = st.columns(2)

start_filter = colA.date_input("Start of range (End Date)", key="range_start")
end_filter = colB.date_input("End of range (End Date)", key="range_end")

# Convert End Date to datetime
df["EndDate_dt"] = pd.to_datetime(df["End Date"], format="%d/%m/%Y")

# Sort by End Date (oldest → newest)
df = df.sort_values("End Date").reset_index(drop=True)

# Apply date range filter
mask = (df["EndDate_dt"] >= pd.to_datetime(start_filter)) & \
       (df["EndDate_dt"] <= pd.to_datetime(end_filter))

filtered_df = df[mask].copy()

# Display summary table
st.subheader("Filtered Sessions")
st.dataframe(filtered_df.drop(columns=["EndDate_dt"]), use_container_width=True)

# Total cost in range
total_cost = filtered_df["Cost"].sum()

# Show summary
st.subheader("Summary")
st.write(f"**Total cost from {start_filter.strftime('%d/%m/%Y')} to {end_filter.strftime('%d/%m/%Y')}: £{total_cost:.2f}**")

