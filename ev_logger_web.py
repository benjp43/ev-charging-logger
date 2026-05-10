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
            "Date","Start","End","Duration (h)","kWh",
            "Night kWh","Day kWh","Cost","Off-Peak %"
        ])
    return pd.read_csv(LOG_FILE, encoding="utf-8-sig")

# -----------------------------
# Save CSV
# -----------------------------
def save_csv(df):
    df.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")

# -----------------------------
# Backfill missing columns
# -----------------------------
def backfill(df, night_rate, day_rate, night_start, night_end):
    for i, row in df.iterrows():
        if pd.isna(row["Night kWh"]) or row["Night kWh"] == "":
            date_dt = datetime.strptime(row["Date"], "%d/%m/%Y")
            start_dt = datetime.combine(date_dt.date(), datetime.strptime(row["Start"], "%H:%M").time())
            end_dt = datetime.combine(date_dt.date(), datetime.strptime(row["End"], "%H:%M").time())
            if end_dt < start_dt:
                end_dt += timedelta(days=1)

            duration_h = float(row["Duration (h)"])
            kwh = float(row["kWh"])

            cost, night_kwh, day_kwh = split_cost(
                start_dt, end_dt, kwh,
                night_rate, day_rate,
                night_start, night_end
            )

            offpeak = int((night_kwh / (night_kwh + day_kwh)) * 100)

            df.at[i, "Night kWh"] = round(night_kwh, 2)
            df.at[i, "Day KWh"] = round(day_kwh, 2)
            df.at[i, "Cost"] = round(cost, 2)
            df.at[i, "Off-Peak %"] = f"{offpeak}%"

    return df

# -----------------------------
# Streamlit UI
# -----------------------------
st.title("⚡ EV Charging Logger (Web Version)")

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
# Add new session
# -----------------------------
st.header("Add Charging Session")

col1, col2, col3 = st.columns(3)

date = col1.date_input("Date")
start = col2.text_input("Start time (HH:MM)")
end = col3.text_input("End time (HH:MM)")

duration = st.text_input("Duration (h or HH:MM)")
kwh = st.number_input("Energy used (kWh)", min_value=0.0)

if st.button("Add session"):
    if not start:
        st.error("Please enter a start time.")
        st.stop()
    if not end and not duration:
        st.error("Please enter an end time or a duration.")
        st.stop()
    date_str = date.strftime("%d/%m/%Y")

    if duration:
        duration_h = duration_to_hours(duration)
        start_dt = datetime.combine(date, datetime.strptime(start, "%H:%M").time())
        end_dt = start_dt + timedelta(hours=duration_h)
        end = end_dt.strftime("%H:%M")
    else:
        start_dt = datetime.combine(date, datetime.strptime(start, "%H:%M").time())
        end_dt = datetime.combine(date, datetime.strptime(end, "%H:%M").time())
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        duration_h = (end_dt - start_dt).total_seconds() / 3600

    cost, night_kwh, day_kwh = split_cost(
        start_dt, end_dt, kwh,
        night_rate, day_rate,
        night_start, night_end
    )

    offpeak = int((night_kwh / (night_kwh + day_kwh)) * 100)

    new_row = {
        "Date": date_str,
        "Start": start,
        "End": end,
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
st.header("Charging History")
st.dataframe(df)

# -----------------------------
# Totals + public comparison
# -----------------------------

# Compute session count and date range
num_sessions = len(df)

if num_sessions > 0:
    first_date = df["Date"].iloc[0]
    last_date = df["Date"].iloc[-1]

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
    start_date = df["Date"].iloc[0].replace("/", ".")
    end_date = df["Date"].iloc[-1].replace("/", ".")
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
    first_date = df["Date"].iloc[0]
    last_date = df["Date"].iloc[-1]
else:
    first_date = last_date = None

total_cost = df["Cost"].sum()

# -----------------------------
# Custom date range summary
# -----------------------------
st.header("Custom date range summary")

colA, colB = st.columns(2)
start_filter = colA.date_input("Start date", key="custom_range_start")
end_filter = colB.date_input("End date", key="custom_range_end")

# Convert df["Date"] to datetime
df_dates = df.copy()
df_dates["Date_dt"] = pd.to_datetime(df_dates["Date"], format="%d/%m/%Y")

# Filter
mask = (df_dates["Date_dt"] >= pd.to_datetime(start_filter)) & \
       (df_dates["Date_dt"] <= pd.to_datetime(end_filter))

df_range = df_dates[mask]

# Compute summary
num_sessions_range = len(df_range)
total_cost_range = df_range["Cost"].sum()

if num_sessions_range > 0:
    first_date_r = df_range["Date"].iloc[0]
    last_date_r = df_range["Date"].iloc[-1]

    st.subheader(
        f"Total home charging cost with {num_sessions_range} sessions "
        f"between {first_date_r} and {last_date_r}: £{total_cost_range:.2f}"
    )
else:
    st.info("No charging sessions found in this date range.")
