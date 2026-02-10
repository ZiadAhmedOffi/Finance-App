import streamlit as st
import pandas as pd
import numpy as np
import math
import psycopg2
from supabase import create_client
import plotly.graph_objects as go
import plotly.express as px

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Fund Financial Model", page_icon="📊", layout="wide")

# ------------------ SENIOR UI/UX STYLING ------------------
st.markdown(
    """
<style>
    /* Matching the border color and style of the Streamlit 'stForm' (Add Deal section).
       Streamlit's default border color for forms/containers is approximately #41454c or 
       rgba(250, 250, 250, 0.2) depending on the exact version. 
       Below uses a neutral gray that is clearly visible and consistent in both themes.
    */
    [data-testid="stMetric"] {
        background-color: transparent;
        border: 1px solid #41454c !important; 
        padding: 20px;
        border-radius: 12px; /* Semi-rounded to match standard containers */
        transition: border-color 0.3s ease;
    }

    [data-testid="stMetric"]:hover {
        border-color: #636EFA !important; /* Subtle highlight on hover */
    }

    /* Sub-header styling for Input Columns */
    .input-header {
        font-weight: bold;
        padding-bottom: 8px;
        border-bottom: 1px solid #41454c;
        margin-bottom: 15px;
        font-size: 1.1rem;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ------------------ HELPERS ------------------
def fmt(x, is_pct=False, is_moic=False):
    if x is None or pd.isna(x):
        return ""
    if is_pct:
        return f"{x:,.2f}%"
    if is_moic:
        return f"{x:,.2f}x"
    # Currency and whole numbers: No decimals, rounded with commas
    return f"{int(round(x)):,}"

def irr(moic, exit_horizon):
    if moic <= 0 or exit_horizon <= 0:
        return np.nan
    return (moic ** (1 / exit_horizon)) - 1

# ------------------ SUPABASE ------------------
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])
conn = psycopg2.connect(st.secrets["SUPABASE_DB_URL"], sslmode="require")

# ------------------ DB OPERATIONS ------------------
def delete_deal_from_db(deal_id):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM deals WHERE id = %s", (deal_id,))
        conn.commit()

# ------------------ AUTH ------------------
if "session" not in st.session_state:
    st.session_state.session = None

def login_ui():
    left_spacer, center_col, right_spacer = st.columns([1, 2, 1])
    with center_col:
        st.markdown("<h1 style='text-align: center;'>🔐 Login</h1>", unsafe_allow_html=True)
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Login", use_container_width=True):
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                if res.session:
                    st.session_state.session = res.session
                    st.rerun()
                else: st.error("Invalid credentials")
        with col2:
            if st.button("Create Account", use_container_width=True):
                res = supabase.auth.sign_up({"email": email, "password": password})
                if res.user: st.success("Account created. Please log in.")
                else: st.error("Signup failed")

if not st.session_state.session:
    login_ui()
    st.stop()

user_id = st.session_state.session.user.id
user_email = st.session_state.session.user.email

# ------------------ DATA LOADING ------------------
with conn.cursor() as c:
    c.execute("insert into public.users (id, email) values (%s, %s) on conflict (id) do nothing", (user_id, user_email))
    conn.commit()

assumptions = pd.read_sql("select * from assumptions where user_id = %s limit 1", conn, params=(user_id,))
if assumptions.empty:
    (investment_period, exit_horizon, min_ticket, max_ticket, target_fund, fund_life, lockup_period, preferred_return, management_fee, admin_cost, t1_exp_moic, t2_exp_moic, t3_exp_moic, tier1_carry, tier2_carry, tier3_carry, target_ownership, expected_dilution, failure_rate, break_even_rate, high_return_rate) = (10, 5, 0.0, 0.0, 0.0, 10, 3.0, 8.0, 2.0, 1.5, 2.5, 1.5, 1.25, 25.0, 25.0, 25.0, 75.0, 15.0, 30.0, 40.0, 35.0)
else:
    r = assumptions.iloc[0]
    investment_period, exit_horizon, min_ticket, max_ticket, target_fund, fund_life, lockup_period, preferred_return, management_fee, admin_cost, t1_exp_moic, t2_exp_moic, t3_exp_moic, tier1_carry, tier2_carry, tier3_carry, target_ownership, expected_dilution, failure_rate, break_even_rate, high_return_rate = (r.investment_period, r.exit_horizon, r.min_ticket, r.max_ticket, r.target_fund, r.actual_fund_life, r.lockup_period, r.preferred_return, r.management_fee, r.admin_cost, r.t1_exp_moic, r.t2_exp_moic, r.t3_exp_moic, r.tier1_carry, r.tier2_carry, r.tier3_carry, r.target_ownership, r.expected_dilution, r.failure_rate, r.break_even_rate, r.high_return_rate)

# ------------------ MAIN TABS ------------------
st.title("📊 Fund Financial Dashboard")
tabs = st.tabs(["📌 Model Inputs", "💼 Deal Prognosis", "📈 Dashboard", "💲 Aggregated Exits" ,"💰 Admin Fee"])

# --- TAB 0: MODEL INPUTS ---
with tabs[0]:
    st.subheader("Model Assumptions")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        
        with c1:
            st.markdown('<div class="input-header">Timeline & Target</div>', unsafe_allow_html=True)
            target_fund = st.number_input("Target Fund Size ($)", 0.0, value=float(target_fund), step=1000.0, format="%0.0f")
            fund_life = st.number_input("Fund Life (Years)", 1, 20, int(fund_life))
            sub_col1, sub_col2, sub_col3 = c1.columns(3)
            with sub_col1:
                investment_period = st.number_input("Investment Period", 1, 20, int(investment_period))
            with sub_col2:
                exit_horizon = st.number_input("Exit Horizon", 1, 20, int(exit_horizon))
            with sub_col3:
                lockup_period = st.number_input("Lockup Period", 1, 20, int(lockup_period))

        with c2:
            st.markdown('<div class="input-header">Terms & Ownership</div>', unsafe_allow_html=True)
            admin_cost = st.number_input("Admin Cost (%)", 0.0, 100.0, float(admin_cost), step=0.1)
            management_fee = st.number_input("Management Fee (%)", 0.0, 100.0, float(management_fee), step=0.1)
            min_ticket = st.number_input("Minimum Ticket ($)", 0.0, value=float(min_ticket), step=1000.0, format="%0.0f")
            max_ticket = st.number_input("Maximum Ticket ($)", 0.0, value=float(max_ticket), step=1000.0, format="%0.0f")
            preferred_return = st.number_input("Preferred Return (%)", 0.0, 100.0, float(preferred_return), step=0.1)
            target_ownership = st.number_input("Target Ownership (%)", 0.0, 100.0, float(target_ownership), step=0.1)

        with c3:
            st.markdown('<div class="input-header">Performance Tiers</div>', unsafe_allow_html=True)
            t1_exp_moic = st.number_input("Tier 1 Expected MOIC", 0.0, 20.0, float(t1_exp_moic), step=0.1)
            t2_exp_moic = st.number_input("Tier 2 Expected MOIC", 0.0, 20.0, float(t2_exp_moic), step=0.1)
            t3_exp_moic = st.number_input("Tier 3 Expected MOIC", 0.0, 20.0, float(t3_exp_moic), step=0.1)
            tier1_carry = st.number_input("Tier 1 Carry (%)", 0.0, 100.0, float(tier1_carry), step=0.1)
            tier2_carry = st.number_input("Tier 2 Carry (%)", 0.0, 100.0, float(tier2_carry), step=0.1)
            tier3_carry = st.number_input("Tier 3 Carry (%)", 0.0, 100.0, float(tier3_carry), step=0.1)

        if st.button("💾 Save Assumptions", use_container_width=True):
            with conn.cursor() as c:
                c.execute("insert into assumptions (user_id, investment_period, exit_horizon, min_ticket, max_ticket, target_fund, actual_fund_life, lockup_period, preferred_return, management_fee, admin_cost, t1_exp_moic, t2_exp_moic, t3_exp_moic, tier1_carry, tier2_carry, tier3_carry, target_ownership, expected_dilution, failure_rate, break_even_rate, high_return_rate) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (user_id) do update set investment_period=excluded.investment_period, exit_horizon=excluded.exit_horizon, min_ticket=excluded.min_ticket, max_ticket=excluded.max_ticket, target_fund=excluded.target_fund, actual_fund_life=excluded.actual_fund_life, lockup_period=excluded.lockup_period, preferred_return=excluded.preferred_return, management_fee=excluded.management_fee, admin_cost=excluded.admin_cost, t1_exp_moic=excluded.t1_exp_moic, t2_exp_moic=excluded.t2_exp_moic, t3_exp_moic=excluded.t3_exp_moic, tier1_carry=excluded.tier1_carry, tier2_carry=excluded.tier2_carry, tier3_carry=excluded.tier3_carry, target_ownership=excluded.target_ownership, expected_dilution=excluded.expected_dilution, failure_rate=excluded.failure_rate, break_even_rate=excluded.break_even_rate, high_return_rate=excluded.high_return_rate", (user_id, investment_period, exit_horizon, min_ticket, max_ticket, target_fund, fund_life, lockup_period, preferred_return, management_fee, admin_cost, t1_exp_moic, t2_exp_moic, t3_exp_moic, tier1_carry, tier2_carry, tier3_carry, target_ownership, expected_dilution, failure_rate, break_even_rate, high_return_rate))
                conn.commit()
            st.success("Assumptions saved successfully!")

    avg_ticket = (min_ticket + max_ticket) / 2 if max_ticket > 0 else 0
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Average Ticket", f"${fmt(avg_ticket)}")
    m_col2.metric("Expected Investors", f"{math.ceil(target_fund / avg_ticket) if avg_ticket > 0 else 0:,}")

# --- TAB 1: DEAL PROGNOSIS ---
with tabs[1]:
    st.subheader("Add Deal")
    with st.form("deal"):
        col_deal1, col_deal2 = st.columns(2)
        with col_deal1:
            company, company_type, industry = st.text_input("Company"), st.text_input("Company Type"), st.text_input("Industry")
            entry_year = st.number_input("Entry Year", 2000, 2100, 2024, format="%d")
            invested = st.number_input("Amount Invested ($)", 0.0, step=1000.0, format="%0.0f")
            entry_val = st.number_input("Entry Valuation ($)", 0.0, step=1000.0, format="%0.0f")
        with col_deal2:
            exit_year = st.number_input("Exit Year", 2000, 2100, entry_year + exit_horizon, format="%d")
            base, down, up = st.number_input("Base Factor", 0.0, 100.0, 3.0, step=0.1), st.number_input("Downside Factor", 0.0, 100.0, 1.5, step=0.1), st.number_input("Upside Factor", 0.0, 100.0, 5.0, step=0.1)
            scenario = st.selectbox("Scenario", ["Base", "Downside", "Upside"])
        if st.form_submit_button("Add Deal", use_container_width=True):
            with conn.cursor() as c:
                c.execute("insert into deals (user_id, company, company_type, industry, entry_year, invested, entry_valuation, exit_year, base_factor, downside_factor, upside_factor, scenario) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (user_id, company, company_type, industry, entry_year, invested, entry_val, exit_year, base, down, up, scenario))
                conn.commit()
            st.success("Deal added")

    df = pd.read_sql("select * from deals where user_id = %s", conn, params=(user_id,))
    if not df.empty:
        df["Holding Period"] = df.exit_year - df.entry_year
        df["Post Money"] = df.entry_valuation + df.invested
        df["Ownership %"] = (df.invested / df["Post Money"]) * 100
        factor = df.apply(lambda r: (r.base_factor if r.scenario == "Base" else r.downside_factor if r.scenario == "Downside" else r.upside_factor), axis=1)
        df["Exit Valuation"], df["Exit Value"] = df["Post Money"] * factor, (df["Post Money"] * factor) * (df["Ownership %"] / 100)
        
        columns_to_show = [
            "company",
            "company_type",
            "industry",
            "entry_year",
            "invested",
            "entry_valuation",
            "exit_year",
            "scenario",
            "Holding Period",
            "Ownership %",
            "Exit Valuation",
            "Exit Value",
        ]

        # 1. Select the columns
        display_df = df[columns_to_show].copy()

        # 2. DO NOT apply fmt to the whole dataframe. 
        # We will only apply it to specific financial columns if needed, 
        # but it's better to let Streamlit's column_config handle it.
        display_df.index += 1  # Start index at 1 for better readability

        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={
                "company": "Company",
                "company_type": "Company Type",
                "industry": "Industry",
                "scenario": "Scenario",
                # Use %d to show the year as a plain integer without commas
                "entry_year": st.column_config.NumberColumn(        
            "Entry Year", 
            format="%d"
        ),
                # Use a dollar format for money columns
                "invested": st.column_config.NumberColumn(
                    "Amount Invested ($)", 
                    format="dollar"
                ),
                "entry_valuation": st.column_config.NumberColumn(
            "Entry Valuation ($)", 
            format="dollar"
        ),
                "exit_year": st.column_config.NumberColumn(
            "Exit Year", 
            format="%d"
        ),
                "Holding Period": "Holding Period (Years)",
                "Ownership %": st.column_config.NumberColumn(
            "Ownership (%)", 
            format="%.2f%%"
        ),
                "Exit Valuation": st.column_config.NumberColumn(
            "Exit Valuation ($)", 
            format="dollar"
        ),
                "Exit Value": st.column_config.NumberColumn(
            "Exit Value ($)", 
            format="dollar"
        ),
            },
        )

        st.divider()
        st.subheader("Delete Deal")
        
        # Create a lookup using company name as display and deal_id as value
        deal_options = df["company"].tolist()
        
        selected_deal = st.selectbox(
            "Select a deal to delete",
            options=deal_options,
            key="deal_delete_select"
        )

        if selected_deal:
            # Get the deal_id for the selected company
            deal_id = df[df["company"] == selected_deal]["id"].iloc[0]
            
            st.warning(f"⚠️ You are about to delete **{selected_deal}**. This action cannot be undone.")
            if st.button("🗑️ Confirm Delete", key="btn_delete_confirm", type="secondary"):
                # Show confirmation dialog
                @st.dialog("Confirm Deletion", width="small")
                def confirm_delete():
                    st.write(f"Are you sure you want to delete **{selected_deal}**?")
                    st.write("This action cannot be undone.")
                    
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("Yes, Delete", type="primary", use_container_width=True):
                            delete_deal_from_db(deal_id)
                            st.session_state.deal_deleted = True
                            st.success("✅ Deal deleted successfully.")
                            st.rerun()
                
                confirm_delete()

        

        # --- ORIGINAL DEAL GRAPHS (UNCHANGED) ---
        st.divider()
        st.subheader("Deal Analytics")
        col_pie1, col_pie2 = st.columns(2)
        with col_pie1:
            type_counts = df['company_type'].value_counts().reset_index()
            fig1 = px.pie(type_counts, values='count', names='company_type', title="Deals by Company Type (%)", hole=0.4)
            st.plotly_chart(fig1, use_container_width=True)
        with col_pie2:
            type_cap = df.groupby('company_type')['invested'].sum().reset_index()
            fig2 = px.pie(type_cap, values='invested', names='company_type', title="Capital Invested by Company Type (%)", hole=0.4)
            st.plotly_chart(fig2, use_container_width=True)

        
        # 5. Holding Period (Horizontal)
        # Aggregate to get the biggest holding period per company
        df_hp = (
            df.groupby('company', as_index=False)['Holding Period']
              .max()
              .sort_values('Holding Period', ascending=True)
        )

        st.write("#### Portfolio Longevity")

        fig5 = px.bar(
            df_hp,
            x='Holding Period',
            y='company',
            orientation='h',
            title="Holding Period by Company (Years)",
            labels={'company': 'Company', 'Holding Period': 'Years'}
        )

        st.plotly_chart(fig5, use_container_width=True)

# --- TAB 2: DASHBOARD ---
with tabs[2]:
    if not df.empty:
        invested, exit_val = df.invested.sum(), df["Exit Value"].sum()
        moic = exit_val / invested if invested > 0 else 0
        fund_irr = irr(moic, exit_horizon)
        c1, c2 = st.columns(2)
        c3, c4, c5 = st.columns(3)
        c1.metric("Total Invested", f"${fmt(invested)}")
        c2.metric("Gross Exit Value", f"${fmt(exit_val)}")
        c3.metric("MOIC", fmt(moic, is_moic=True))
        c4.metric("IRR", fmt(fund_irr * 100, is_pct=True) if not pd.isna(fund_irr) else "N/A")
        c5.metric("Total Deals", f"{len(df)}")

        st.write("#### Investment Velocity")
        yearly_stats = df.groupby('entry_year').agg({'invested': 'sum', 'id': 'count'}).reset_index().sort_values('entry_year')
        yearly_stats['cum_invested'], yearly_stats['cum_deals'] = yearly_stats['invested'].cumsum(), yearly_stats['id'].cumsum()
        cv1, cv2 = st.columns(2)
        with cv1:
            fig_deals = go.Figure()
            fig_deals.add_trace(go.Bar(x=yearly_stats['entry_year'], y=yearly_stats['id'], name="Deals per Year", marker_color='#EF553B'))
            fig_deals.add_trace(go.Scatter(x=yearly_stats['entry_year'], y=yearly_stats['cum_deals'], name="Total Deals (Cum)", line=dict(color='white', width=3, dash='dash')))
            st.plotly_chart(fig_deals, use_container_width=True)
        with cv2:
            fig_inv = go.Figure()
            fig_inv.add_trace(go.Bar(x=yearly_stats['entry_year'], y=yearly_stats['invested'], name="Invested per Year", marker_color='#636EFA'))
            fig_inv.add_trace(go.Scatter(x=yearly_stats['entry_year'], y=yearly_stats['cum_invested'], name="Total Invested (Cum)", line=dict(color='gold', width=3)))
            st.plotly_chart(fig_inv, use_container_width=True)

        st.write("#### Capital Appreciation (Linear Projection)")
        if not yearly_stats.empty:
            years = sorted(df['entry_year'].unique().tolist())
            appreciation_line = np.linspace(yearly_stats['cum_invested'].iloc[0], df["Exit Value"].sum(), len(years))
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=years, y=yearly_stats['cum_invested'], name="Cumulative Invested", mode='lines+markers', line=dict(color='#00CC96', width=3)))
            fig4.add_trace(go.Scatter(x=years, y=appreciation_line, name="Appreciation Projection", line=dict(color='#AB63FA', width=4, dash='dot')))
            st.plotly_chart(fig4, use_container_width=True)


# --- TAB 3: AGGREGATED EXITS ---
with tabs[3]:
    if not df.empty:
        total_invested, base_gev = df.invested.sum(), df["Exit Value"].sum()
        admin_cost_val = (admin_cost / 100) * target_fund
        total_fees = (admin_cost_val * investment_period) + admin_cost_val
        st.metric("Total Invested Capital", f"${fmt(total_invested)}")
        
        scenarios, multipliers, data = ["**Base Case**", "**Upside Case**", "**High Growth Case**"], [1.0, 1.5, 2.0], []
        for s_name, mult in zip(scenarios, multipliers):
            gev = base_gev * mult
            pbc, g_moic = gev - total_invested, (gev / total_invested if total_invested > 0 else 0)
            carry_pct = tier1_carry if g_moic < t2_exp_moic else (tier2_carry if g_moic < t3_exp_moic else tier3_carry)
            carry_amt = max(0, pbc * (carry_pct / 100))
            net = gev - carry_amt - total_fees
            r_moic = net / total_invested if total_invested > 0 else 0
            data.append({"Scenario": s_name, "GEV": gev, "PBC": pbc, "G_MOIC": g_moic, "CP": carry_pct, "CA": carry_amt, "TF": total_fees, "Net": net, "R_MOIC": r_moic, "IRR": irr(r_moic, exit_horizon)})
        
        final_rows = []
        for label, key, unit in [("Gross Exit Value", "GEV", "$"), ("Profit Before Carry", "PBC", "$"), ("Gross MOIC", "G_MOIC", "x"), ("Carry (%)", "CP", "%"), ("Carry Amount", "CA", "$"), ("Total Fees", "TF", "$"), ("Net to Investors", "Net", "$"), ("Real MOIC", "R_MOIC", "x"), ("IRR", "IRR", "%")]:
            row = {"**Metric**": label}
            for entry in data:
                val = entry[key]
                if unit == "%": row[entry["Scenario"]] = fmt(val * 100 if key == "IRR" else val, is_pct=True)
                elif unit == "x": row[entry["Scenario"]] = fmt(val, is_moic=True)
                else: row[entry["Scenario"]] = f"${fmt(val)}"
            final_rows.append(row)
        st.table(pd.DataFrame(final_rows).set_index("**Metric**"))

        # --- ORIGINAL SCENARIO GRAPH (UNCHANGED) ---
        st.divider()
        scenario_labels = [d["Scenario"].replace("**", "") for d in data]
        irrs = [d["IRR"] * 100 for d in data]
        fig6 = go.Figure()
        fig6.add_trace(go.Bar(x=scenario_labels, y=[total_invested]*3, name="Invested Capital", marker_color='lightslategray'))
        fig6.add_trace(go.Bar(x=scenario_labels, y=[d["GEV"] for d in data], name="Gross Exit Value", marker_color='royalblue'))
        fig6.add_trace(go.Scatter(x=scenario_labels, y=irrs, name="IRR (%)", yaxis='y2', line=dict(color='firebrick', width=4), mode='lines+markers+text', text=[f"{v:.1f}%" for v in irrs], textposition="top center"))
        fig6.update_layout(yaxis=dict(title="Amount ($)"), yaxis2=dict(title="IRR (%)", overlaying='y', side='right', range=[0, max(irrs)*1.2 if irrs else 100]), barmode='group', legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig6, use_container_width=True)

# --- TAB 4: ADMIN FEE ---
with tabs[4]:
    admin_cost = (admin_cost / 100) * target_fund
    operations_fee = admin_cost
    management_fee = admin_cost * investment_period

    fee_df = pd.DataFrame(
        {
            "Fee Type": ["Admin Cost", "Operations Fee", "Management Fee"],
            "Amount ($)": [admin_cost, operations_fee, management_fee],
        }
    )

    fee_df["Amount ($)"] = fee_df["Amount ($)"].apply(fmt)
    fee_df.index += 1  # Start index at 1 for better readability
    st.table(fee_df)