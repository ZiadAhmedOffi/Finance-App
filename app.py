import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import bcrypt
import math

# ------------------ PAGE CONFIG ------------------
st.set_page_config(
    page_title="Fund Financial Model",
    page_icon="📊",
    layout="wide"
)

# ------------------ STYLES ------------------
st.markdown("""
<style>
body { background-color: #0f172a; color: #e5e7eb; }
[data-testid="stMetric"] {
    background-color: #111827;
    padding: 18px;
    border-radius: 12px;
}
h1, h2, h3 { color: #e5e7eb; }
</style>
""", unsafe_allow_html=True)

# ------------------ HELPERS ------------------
def fmt(x):
    if x is None or pd.isna(x):
        return ""
    return f"{x:,.3f}".rstrip("0").rstrip(".")

# ------------------ DATABASE ------------------
conn = sqlite3.connect("fund.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password BLOB
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS assumptions (
    id INTEGER PRIMARY KEY,
    fund_life INTEGER,
    exit_horizon INTEGER,
    min_ticket REAL,
    max_ticket REAL,
    target_fund REAL,
    actual_fund_life INTEGER
)
""")

# Add new column if it doesn't exist
try:
    c.execute("ALTER TABLE assumptions ADD COLUMN actual_fund_life INTEGER DEFAULT 10")
except sqlite3.OperationalError:
    pass

c.execute("""
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT,
    entry_year INTEGER,
    invested REAL,
    entry_valuation REAL,
    exit_year INTEGER,
    base_factor REAL,
    downside_factor REAL,
    upside_factor REAL,
    scenario TEXT,
    company_type TEXT,
    industry TEXT
)
""")

# Add new columns if they don't exist
try:
    c.execute("ALTER TABLE deals ADD COLUMN company_type TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass
try:
    c.execute("ALTER TABLE deals ADD COLUMN industry TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass

conn.commit()

# ------------------ AUTH ------------------
def hash_password(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt())

def check_password(p, h):
    return bcrypt.checkpw(p.encode(), h)

def login():
    st.title("🔐 Login")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        c.execute("SELECT password FROM users WHERE username=?", (u,))
        r = c.fetchone()
        if r and check_password(p, r[0]):
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Invalid credentials")

    if st.button("Create Account"):
        try:
            c.execute("INSERT INTO users VALUES (?,?)", (u, hash_password(p)))
            conn.commit()
            st.success("Account created")
        except:
            st.error("User exists")

# ------------------ IRR ------------------
def irr(moic, exit_horizon):
    if moic <= 0 or exit_horizon <= 0:
        return np.nan
    return (moic ** (1 / exit_horizon)) - 1

# ------------------ AUTH CHECK ------------------
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    login()
    st.stop()

# ------------------ LOAD ASSUMPTIONS ------------------
c.execute("SELECT fund_life, exit_horizon, min_ticket, max_ticket, target_fund, actual_fund_life FROM assumptions LIMIT 1")
row = c.fetchone()

investment_period, exit_horizon, min_ticket, max_ticket, target_fund, fund_life = row if row else (10, 5, 0.0, 0.0, 0.0, 10)

# ------------------ APP ------------------
st.title("📊 Fund Financial Dashboard")
tabs = st.tabs(["📌 Model Inputs", "💼 Deal Prognosis", "📈 Dashboard", "💰 Admin Fee"])

# ------------------ MODEL INPUTS ------------------
with tabs[0]:
    st.subheader("Model Inputs")

    investment_period = st.number_input("Investment Period (Years)", 1, 20, investment_period)
    fund_life = st.number_input("Fund Life (Years)", 1, 20, fund_life)
    exit_horizon = st.number_input("Exit Horizon (Years)", 1, 20, exit_horizon)
    min_ticket = st.number_input("Minimum Ticket ($)", 0.0, value=min_ticket, step=10_000.0)
    max_ticket = st.number_input("Maximum Ticket ($)", 0.0, value=max_ticket, step=10_000.0)
    target_fund = st.number_input("Target Fund Size ($)", 0.0, value=target_fund, step=100_000.0)

    if st.button("Save Assumptions"):
        c.execute("DELETE FROM assumptions")
        c.execute("""
            INSERT INTO assumptions VALUES (1,?,?,?,?,?,?)
        """, (investment_period, exit_horizon, min_ticket, max_ticket, target_fund, fund_life))
        conn.commit()
        st.success("Saved")

    avg_ticket = (min_ticket + max_ticket) / 2 if max_ticket > 0 else 0
    expected_investors = math.ceil(target_fund / avg_ticket) if avg_ticket > 0 else 0

    col1, col2 = st.columns(2)
    col1.metric("Average Ticket", f"${fmt(avg_ticket)}")
    col2.metric("Expected Investors", f"{expected_investors:,}")

# ------------------ DEAL PROGNOSIS ------------------
with tabs[1]:
    st.subheader("Add Deal Prognosis")

    with st.form("deal"):
        company = st.text_input("Company")
        company_type = st.text_input("Company Type")
        industry = st.text_input("Industry")
        entry_year = st.number_input("Entry Year", 2000, 2100, 2024)
        invested = st.number_input("Amount Invested ($)", 0.0)
        entry_val = st.number_input("Entry Valuation ($)", 0.0)
        exit_year = st.number_input("Exit Year", 2000, 2100, entry_year + exit_horizon)
        base = st.number_input("Base Factor", 0.0, 100.0, 3.0)
        down = st.number_input("Downside Factor", 0.0, 100.0, 1.5)
        up = st.number_input("Upside Factor", 0.0, 100.0, 5.0)
        scenario = st.selectbox("Scenario", ["Base", "Downside", "Upside"])

        if st.form_submit_button("Add Deal"):
            c.execute("""
                INSERT INTO deals VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?)
            """, (company, entry_year, invested, entry_val, exit_year, base, down, up, scenario, company_type, industry))
            conn.commit()
            st.success("Deal added")

    st.subheader("Deal Prognosis")

    df = pd.read_sql("SELECT * FROM deals", conn)

    if not df.empty:
        df["Index"] = range(1, len(df) + 1)
        df["Holding Period"] = df.exit_year - df.entry_year
        df["Post Money"] = df.entry_valuation + df.invested
        df["Ownership %"] = (df.invested / df["Post Money"]) * 100

        factor = df.apply(
            lambda r: r.base_factor if r.scenario == "Base"
            else r.downside_factor if r.scenario == "Downside"
            else r.upside_factor,
            axis=1
        )

        df["Exit Valuation"] = df["Post Money"] * factor
        df["Exit Value"] = df["Exit Valuation"] * (df["Ownership %"] / 100)

        display_df = df.copy()
        for col in display_df.columns:
            if display_df[col].dtype != object:
                if col in ['entry_year', 'exit_year']:
                    display_df[col] = display_df[col].astype(int).astype(str)
                elif col == 'Ownership %':
                    display_df[col] = display_df[col].apply(lambda x: f"{fmt(x)}%" if not pd.isna(x) else "")
                elif col == 'Index':
                    display_df[col] = display_df[col].astype(str)
                else:
                    display_df[col] = display_df[col].apply(fmt)

        display_df.index = range(1, len(display_df) + 1)
        st.dataframe(display_df, use_container_width=True)

        for i, r in df.iterrows():
            if st.button(f"❌ Remove Deal {r.Index}: {r.company}", key=r.id):
                c.execute("DELETE FROM deals WHERE id=?", (r.id,))
                conn.commit()
                st.rerun()

# ------------------ DASHBOARD ------------------
with tabs[2]:
    st.subheader("Fund Overview")

    if not df.empty:
        invested = df.invested.sum()
        exit_val = df["Exit Value"].sum()
        moic = exit_val / invested if invested > 0 else 0

        flows = []
        for _, r in df.iterrows():
            flows.append(-r.invested)
            flows.append(r["Exit Value"])

        fund_irr = irr(moic, exit_horizon)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Invested", f"${fmt(invested)}")
        c2.metric("Gross Exit Value", f"${fmt(exit_val)}")
        c3.metric("MOIC", f"{fmt(moic)}x")
        c4.metric("IRR", f"{fmt(fund_irr * 100)}%" if fund_irr == fund_irr else "N/A")
        c5.metric("Total Deals", f"{len(df)}")

# ------------------ ADMIN FEE ------------------
with tabs[3]:
    st.subheader("Administrative Fees")

    admin_cost = 0.05 * target_fund
    operations_fee = admin_cost
    management_fee = admin_cost * investment_period

    fee_data = {
        "Fee Type": ["Admin Cost", "Operations Fee", "Management Fee Over Investment Period"],
        "Amount ($)": [admin_cost, operations_fee, management_fee]
    }

    fee_df = pd.DataFrame(fee_data)
    fee_df["Amount ($)"] = fee_df["Amount ($)"].apply(fmt)
    fee_df.index = range(1, len(fee_df) + 1)

    st.table(fee_df)
