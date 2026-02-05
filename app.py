import streamlit as st
import pandas as pd
import numpy as np
import math
import psycopg2
from supabase import create_client

# ------------------ CONFIG ------------------
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

def irr(moic, exit_horizon):
    if moic <= 0 or exit_horizon <= 0:
        return np.nan
    return (moic ** (1 / exit_horizon)) - 1

# ------------------ SUPABASE ------------------
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_ANON_KEY"]
)

conn = psycopg2.connect(
    st.secrets["SUPABASE_DB_URL"],
    sslmode="require"
)

# ------------------ AUTH ------------------
if "session" not in st.session_state:
    st.session_state.session = None

def login_ui():
    st.title("🔐 Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Login"):
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            if res.session:
                st.session_state.session = res.session
                st.rerun()
            else:
                st.error("Invalid credentials")

    with col2:
        if st.button("Create Account"):
            res = supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            if res.user:
                st.success("Account created. Please log in.")
            else:
                st.error("Signup failed")

if not st.session_state.session:
    login_ui()
    st.stop()

user_id = st.session_state.session.user.id
user_email = st.session_state.session.user.email

# ------------------ ENSURE USER ROW ------------------
with conn.cursor() as c:
    c.execute("""
        insert into public.users (id, email)
        values (%s, %s)
        on conflict (id) do nothing
    """, (user_id, user_email))
    conn.commit()

# ------------------ LOAD ASSUMPTIONS ------------------
assumptions = pd.read_sql("""
    select * from assumptions
    where user_id = %s
    limit 1
""", conn, params=(user_id,))

if assumptions.empty:
    investment_period, exit_horizon, min_ticket, max_ticket, target_fund, fund_life = (10, 5, 0.0, 0.0, 0.0, 10)
else:
    r = assumptions.iloc[0]
    investment_period = r.investment_period
    exit_horizon = r.exit_horizon
    min_ticket = r.min_ticket
    max_ticket = r.max_ticket
    target_fund = r.target_fund
    fund_life = r.actual_fund_life

# ------------------ APP ------------------
st.title("📊 Fund Financial Dashboard")
tabs = st.tabs(["📌 Model Inputs", "💼 Deal Prognosis", "📈 Dashboard", "💰 Admin Fee"])

st.write(st.secrets.keys())

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
        with conn.cursor() as c:
            c.execute("""
                insert into assumptions
                (user_id, investment_period, exit_horizon, min_ticket, max_ticket, target_fund, actual_fund_life)
                values (%s,%s,%s,%s,%s,%s,%s)
                on conflict (user_id) do update set
                    investment_period = excluded.investment_period,
                    exit_horizon = excluded.exit_horizon,
                    min_ticket = excluded.min_ticket,
                    max_ticket = excluded.max_ticket,
                    target_fund = excluded.target_fund,
                    actual_fund_life = excluded.actual_fund_life
            """, (user_id, investment_period, exit_horizon, min_ticket, max_ticket, target_fund, fund_life))
            conn.commit()
        st.success("Saved")

    avg_ticket = (min_ticket + max_ticket) / 2 if max_ticket > 0 else 0
    expected_investors = math.ceil(target_fund / avg_ticket) if avg_ticket > 0 else 0

    c1, c2 = st.columns(2)
    c1.metric("Average Ticket", f"${fmt(avg_ticket)}")
    c2.metric("Expected Investors", f"{expected_investors:,}")

# ------------------ DEAL PROGNOSIS ------------------
with tabs[1]:
    st.subheader("Add Deal")

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
            with conn.cursor() as c:
                c.execute("""
                    insert into deals
                    (user_id, company, company_type, industry, entry_year, invested,
                     entry_valuation, exit_year, base_factor, downside_factor,
                     upside_factor, scenario)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (user_id, company, company_type, industry, entry_year, invested,
                      entry_val, exit_year, base, down, up, scenario))
                conn.commit()
            st.success("Deal added")

    df = pd.read_sql("select * from deals where user_id = %s", conn, params=(user_id,))

    if not df.empty:
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
                display_df[col] = display_df[col].apply(fmt)

        st.dataframe(display_df, use_container_width=True)

        for _, r in df.iterrows():
            if st.button(f"❌ Remove {r.company}", key=str(r.id)):
                with conn.cursor() as c:
                    c.execute("delete from deals where id = %s and user_id = %s", (r.id, user_id))
                    conn.commit()
                st.rerun()

# ------------------ DASHBOARD ------------------
with tabs[2]:
    if not df.empty:
        invested = df.invested.sum()
        exit_val = df["Exit Value"].sum()
        moic = exit_val / invested if invested > 0 else 0
        fund_irr = irr(moic, exit_horizon)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Invested", f"${fmt(invested)}")
        c2.metric("Gross Exit Value", f"${fmt(exit_val)}")
        c3.metric("MOIC", f"{fmt(moic)}x")
        c4.metric("IRR", f"{fmt(fund_irr * 100)}%" if fund_irr == fund_irr else "N/A")
        c5.metric("Total Deals", f"{len(df)}")

# ------------------ ADMIN FEE ------------------
with tabs[3]:
    admin_cost = 0.05 * target_fund
    operations_fee = admin_cost
    management_fee = admin_cost * investment_period

    fee_df = pd.DataFrame({
        "Fee Type": ["Admin Cost", "Operations Fee", "Management Fee"],
        "Amount ($)": [admin_cost, operations_fee, management_fee]
    })

    fee_df["Amount ($)"] = fee_df["Amount ($)"].apply(fmt)
    st.table(fee_df)
