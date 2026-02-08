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

# ------------------ STYLES ------------------
st.markdown(
    """
<style>
body { background-color: #0f172a; color: #e5e7eb; }
[data-testid="stMetric"] {
    background-color: #111827;
    padding: 18px;
    border-radius: 12px;
}
h1, h2, h3 { color: #e5e7eb; }
</style>
""",
    unsafe_allow_html=True,
)


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
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])

conn = psycopg2.connect(st.secrets["SUPABASE_DB_URL"], sslmode="require")

# ------------------ AUTH ------------------
if "session" not in st.session_state:
    st.session_state.session = None


def login_ui():
    # 1. Create three columns with a wide center column
    left_spacer, center_col, right_spacer = st.columns([1, 2, 1])

    with center_col:
        # 2. Use HTML to center the title text
        st.markdown("<h1 style='text-align: center;'>🔐 Login</h1>", unsafe_allow_html=True)

        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Login", use_container_width=True):
                res = supabase.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
                if res.session:
                    st.session_state.session = res.session
                    st.rerun()
                else:
                    st.error("Invalid credentials")

        with col2:
            if st.button("Create Account", use_container_width=True):
                res = supabase.auth.sign_up({"email": email, "password": password})
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
    c.execute(
        """
        insert into public.users (id, email)
        values (%s, %s)
        on conflict (id) do nothing
    """,
        (user_id, user_email),
    )
    conn.commit()

# ------------------ LOAD ASSUMPTIONS ------------------
assumptions = pd.read_sql(
    """
    select * from assumptions
    where user_id = %s
    limit 1
""",
    conn,
    params=(user_id,),
)

if assumptions.empty:
    (
        investment_period,
        exit_horizon,
        min_ticket,
        max_ticket,
        target_fund,
        fund_life,
        lockup_period,
        preferred_return,
        management_fee,
        admin_cost,
        t1_exp_moic,
        t2_exp_moic,
        t3_exp_moic,
        tier1_carry,
        tier2_carry,
        tier3_carry,
        target_ownership,
        expected_dilution,
        failure_rate,
        break_even_rate,
        high_return_rate,
    ) = (
        10,
        5,
        0.0,
        0.0,
        0.0,
        10,
        3.0,
        8.0,
        2.0,
        1.5,
        2.5,
        1.5,
        1.25,
        25.0,
        25.0,
        25.0,
        75.0,
        15.0,
        30.0,
        40.0,
        35.0,
    )
else:
    r = assumptions.iloc[0]
    investment_period = r.investment_period
    exit_horizon = r.exit_horizon
    min_ticket = r.min_ticket
    max_ticket = r.max_ticket
    target_fund = r.target_fund
    fund_life = r.actual_fund_life
    lockup_period = r.lockup_period
    preferred_return = r.preferred_return
    management_fee = r.management_fee
    admin_cost = r.admin_cost
    t1_exp_moic = r.t1_exp_moic
    t2_exp_moic = r.t2_exp_moic
    t3_exp_moic = r.t3_exp_moic
    tier1_carry = r.tier1_carry
    tier2_carry = r.tier2_carry
    tier3_carry = r.tier3_carry
    target_ownership = r.target_ownership
    expected_dilution = r.expected_dilution
    failure_rate = r.failure_rate
    break_even_rate = r.break_even_rate
    high_return_rate = r.high_return_rate


# ------------------ DB OPERATIONS ------------------
def delete_deal_from_db(deal_id):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM deals WHERE id = %s", (deal_id,))
        conn.commit()


# ------------------ APP ------------------
st.title("📊 Fund Financial Dashboard")
tabs = st.tabs(["📌 Model Inputs", "💼 Deal Prognosis", "📈 Dashboard", "💲 Aggregated Exits" ,"💰 Admin Fee"])

# ------------------ MODEL INPUTS ------------------
with tabs[0]:
    st.subheader("Model Assumptions")

    # Split inputs into two columns
    col_input1, col_input2 = st.columns(2)

    with col_input1:
        investment_period = st.number_input(
            "Investment Period (Years)", 1, 20, investment_period
        )
        fund_life = st.number_input("Fund Life (Years)", 1, 20, fund_life)
        exit_horizon = st.number_input("Exit Horizon (Years)", 1, 20, exit_horizon)
        min_ticket = st.number_input(
            "Minimum Ticket ($)", 0.0, value=min_ticket, step=10_000.0
        )
        max_ticket = st.number_input(
            "Maximum Ticket ($)", 0.0, value=max_ticket, step=10_000.0
        )
        target_fund = st.number_input(
            "Target Fund Size ($)", 0.0, value=target_fund, step=100_000.0
        )
        lockup_period = st.number_input("Lockup Period (Years)", 1, 20, lockup_period)
        preferred_return = st.number_input(
            "Preferred Return (%)", 0.0, 100.0, preferred_return
        )
        management_fee = st.number_input("Management Fee (%)", 0.0, 100.0, management_fee)
        admin_cost = st.number_input("Admin Cost (%)", 0.0, 100.0, admin_cost)
        target_ownership = st.number_input(
            "Target Ownership (%)", 0.0, 100.0, target_ownership
        )

    with col_input2:
        t1_exp_moic = st.number_input("Top 1 Expected MOIC", 0.0, 20.0, t1_exp_moic)
        t2_exp_moic = st.number_input("Top 2-5 Expected MOIC", 0.0, 20.0, t2_exp_moic)
        t3_exp_moic = st.number_input("Top 6-20 Expected MOIC", 0.0, 20.0, t3_exp_moic)
        tier1_carry = st.number_input("Tier 1 Carry (%)", 0.0, 100.0, tier1_carry)
        tier2_carry = st.number_input("Tier 2 Carry (%)", 0.0, 100.0, tier2_carry)
        tier3_carry = st.number_input("Tier 3 Carry (%)", 0.0, 100.0, tier3_carry)
        expected_dilution = st.number_input(
            "Expected Dilution (%)", 0.0, 100.0, expected_dilution
        )
        failure_rate = st.number_input("Failure Rate (%)", 0.0, 100.0, failure_rate)
        break_even_rate = st.number_input(
            "Break-even Rate (%)", 0.0, 100.0, break_even_rate
        )
        high_return_rate = st.number_input(
            "High Return Rate (%)", 0.0, 100.0, high_return_rate
        )

    # Save button centered below columns
    if st.button("💾 Save Assumptions", use_container_width=True):
        with conn.cursor() as c:
            c.execute(
                """
                insert into assumptions
                (user_id, investment_period, exit_horizon, min_ticket, max_ticket, target_fund, actual_fund_life, lockup_period, preferred_return, management_fee, admin_cost, t1_exp_moic, t2_exp_moic, t3_exp_moic, tier1_carry, tier2_carry, tier3_carry, target_ownership, expected_dilution, failure_rate, break_even_rate, high_return_rate)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (user_id) do update set
                    investment_period = excluded.investment_period,
                    exit_horizon = excluded.exit_horizon,
                    min_ticket = excluded.min_ticket,
                    max_ticket = excluded.max_ticket,
                    target_fund = excluded.target_fund,
                    actual_fund_life = excluded.actual_fund_life,
                    lockup_period = excluded.lockup_period,
                    preferred_return = excluded.preferred_return,
                    management_fee = excluded.management_fee,
                    admin_cost = excluded.admin_cost,
                    t1_exp_moic = excluded.t1_exp_moic,
                    t2_exp_moic = excluded.t2_exp_moic,
                    t3_exp_moic = excluded.t3_exp_moic,
                    tier1_carry = excluded.tier1_carry,
                    tier2_carry = excluded.tier2_carry,
                    tier3_carry = excluded.tier3_carry,
                    target_ownership = excluded.target_ownership,
                    expected_dilution = excluded.expected_dilution,
                    failure_rate = excluded.failure_rate,
                    break_even_rate = excluded.break_even_rate,
                    high_return_rate = excluded.high_return_rate
            """,
                (
                    user_id, investment_period, exit_horizon, min_ticket, max_ticket,
                    target_fund, fund_life, lockup_period, preferred_return,
                    management_fee, admin_cost, t1_exp_moic, t2_exp_moic,
                    t3_exp_moic, tier1_carry, tier2_carry, tier3_carry,
                    target_ownership, expected_dilution, failure_rate,
                    break_even_rate, high_return_rate,
                ),
            )
            conn.commit()
        st.success("Assumptions saved successfully!")

    st.divider()

    # Metrics section
    avg_ticket = (min_ticket + max_ticket) / 2 if max_ticket > 0 else 0
    expected_investors = math.ceil(target_fund / avg_ticket) if avg_ticket > 0 else 0

    m1, m2 = st.columns(2)
    m1.metric("Average Ticket", f"${fmt(avg_ticket)}")
    m2.metric("Expected Investors", f"{expected_investors:,}")

# ------------------ DEAL PROGNOSIS ------------------
with tabs[1]:
    st.subheader("Add Deal")

    with st.form("deal"):
        # Create two columns for the input fields
        col_deal1, col_deal2 = st.columns(2)

        with col_deal1:
            company = st.text_input("Company")
            company_type = st.text_input("Company Type")
            industry = st.text_input("Industry")
            entry_year = st.number_input("Entry Year", 2000, 2100, 2024)
            invested = st.number_input("Amount Invested ($)", 0.0)
            entry_val = st.number_input("Entry Valuation ($)", 0.0)

        with col_deal2:
            exit_year = st.number_input("Exit Year", 2000, 2100, entry_year + exit_horizon)
            base = st.number_input("Base Factor", 0.0, 100.0, 3.0)
            down = st.number_input("Downside Factor", 0.0, 100.0, 1.5)
            up = st.number_input("Upside Factor", 0.0, 100.0, 5.0)
            scenario = st.selectbox("Scenario", ["Base", "Downside", "Upside"])

        # The submit button stays outside the columns but inside the form
        if st.form_submit_button("Add Deal", use_container_width=True):
            with conn.cursor() as c:
                c.execute(
                    """
                    insert into deals
                    (user_id, company, company_type, industry, entry_year, invested,
                     entry_valuation, exit_year, base_factor, downside_factor,
                     upside_factor, scenario)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                    (
                        user_id,
                        company,
                        company_type,
                        industry,
                        entry_year,
                        invested,
                        entry_val,
                        exit_year,
                        base,
                        down,
                        up,
                        scenario,
                    ),
                )
                conn.commit()
            st.success("Deal added")

    df = pd.read_sql("select * from deals where user_id = %s", conn, params=(user_id,))

    if not df.empty:
        df["Holding Period"] = df.exit_year - df.entry_year
        df["Post Money"] = df.entry_valuation + df.invested
        df["Ownership %"] = (df.invested / df["Post Money"]) * 100

        factor = df.apply(
            lambda r: (
                r.base_factor
                if r.scenario == "Base"
                else r.downside_factor if r.scenario == "Downside" else r.upside_factor
            ),
            axis=1,
        )

        df["Exit Valuation"] = df["Post Money"] * factor
        df["Exit Value"] = df["Exit Valuation"] * (df["Ownership %"] / 100)

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

            col1, col2 = st.columns(2)
            
            with col1:
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

    st.divider()
    st.subheader("Deal Analytics")
    
    # Row 1: Pie Charts
    col_pie1, col_pie2 = st.columns(2)
        
    with col_pie1:
        # 1. Company Types by Number of Deals
        type_counts = df['company_type'].value_counts().reset_index()
        fig1 = px.pie(type_counts, values='count', names='company_type', 
                      title="Deals by Company Type (%)", hole=0.4)
        st.plotly_chart(fig1, use_container_width=True)
        
    with col_pie2:
        # 2. Company Types by Capital Invested
        type_cap = df.groupby('company_type')['invested'].sum().reset_index()
        fig2 = px.pie(type_cap, values='invested', names='company_type', 
                      title="Capital Invested by Company Type (%)", hole=0.4)
        st.plotly_chart(fig2, use_container_width=True)
    # 3. Investment Velocity (Split into two columns)
    st.write("#### Investment Velocity")
    yearly_stats = df.groupby('entry_year').agg({'invested': 'sum', 'id': 'count'}).reset_index()
    yearly_stats = yearly_stats.sort_values('entry_year')
    yearly_stats['cum_invested'] = yearly_stats['invested'].cumsum()
    yearly_stats['cum_deals'] = yearly_stats['id'].cumsum()

    # Create two columns for the Velocity metrics
    col_vel1, col_vel2 = st.columns(2)

    with col_vel1:
        # --- Graph 3a: Deal Count Velocity ---
        fig_deals = go.Figure()
        fig_deals.add_trace(go.Bar(
            x=yearly_stats['entry_year'], 
            y=yearly_stats['id'], 
            name="Deals per Year", 
            marker_color='#EF553B'
        ))
        fig_deals.add_trace(go.Scatter(
            x=yearly_stats['entry_year'], 
            y=yearly_stats['cum_deals'], 
            name="Total Deals (Cum)", 
            line=dict(color='white', width=3, dash='dash')
        ))
        fig_deals.update_layout(
            title="Deal Velocity (Count)",
            xaxis=dict(type='category', title="Year"),
            yaxis=dict(title="Number of Deals"),
            legend=dict(orientation="h", y=-0.2),
            margin=dict(t=50, b=50, l=25, r=25)
        )
        st.plotly_chart(fig_deals, use_container_width=True)
    with col_vel2:
        # --- Graph 3b: Capital Deployment Velocity ---
        fig_inv = go.Figure()
        fig_inv.add_trace(go.Bar(
            x=yearly_stats['entry_year'], 
            y=yearly_stats['invested'], 
            name="Invested per Year", 
            marker_color='#636EFA'
        ))
        fig_inv.add_trace(go.Scatter(
            x=yearly_stats['entry_year'], 
            y=yearly_stats['cum_invested'], 
            name="Total Invested (Cum)", 
            line=dict(color='gold', width=3)
        ))
        fig_inv.update_layout(
            title="Capital Deployment ($)",
            xaxis=dict(type='category', title="Year"),
            yaxis=dict(title="Amount ($)"),
            legend=dict(orientation="h", y=-0.2),
            margin=dict(t=50, b=50, l=25, r=25)
        )
        st.plotly_chart(fig_inv, use_container_width=True)

    # 4. Appreciation Projection (REVISED)
    st.write("#### Capital Appreciation (Linear Projection)")
    total_gev = df["Exit Value"].sum()
        
    if not yearly_stats.empty:
        start_val = yearly_stats['cum_invested'].iloc[0]
        years = sorted(df['entry_year'].unique().tolist())
            
        if len(years) > 1:
            steps = len(years)
            appreciation_line = np.linspace(start_val, total_gev, steps)
            
            fig4 = go.Figure()
            # Removed fill='tozeroy' to make it a simple line
            fig4.add_trace(go.Scatter(
                x=years, 
                y=yearly_stats['cum_invested'], 
                name="Cumulative Invested",
                mode='lines+markers',
                line=dict(color='#00CC96', width=3)
            ))
            fig4.add_trace(go.Scatter(
                x=years, 
                y=appreciation_line, 
                name="Appreciation Projection", 
                line=dict(color='#AB63FA', width=4, dash='dot')
            ))
            
            fig4.update_layout(
                title="Investment Basis vs. Projected Exit Value", 
                xaxis=dict(type='category'),
                yaxis_title="Value ($)",
                legend=dict(orientation="h", y=-0.2)
            )
            st.plotly_chart(fig4, use_container_width=True)
    # 5. Holding Period (Horizontal)
    st.write("#### Portfolio Longevity")
    df_hp = df.sort_values('Holding Period', ascending=True) # Ascending for correct top-down bar chart
    fig5 = px.bar(df_hp, x='Holding Period', y='company', orientation='h', 
                  title="Holding Period by Company (Years)",
                  labels={'company': 'Company', 'Holding Period': 'Years'})
    st.plotly_chart(fig5, use_container_width=True)


# ------------------ DASHBOARD ------------------
with tabs[2]:
    if not df.empty:
        invested = df.invested.sum()
        exit_val = df["Exit Value"].sum()
        moic = exit_val / invested if invested > 0 else 0
        fund_irr = irr(moic, exit_horizon)

        c1, c2 = st.columns(2)
        c3, c4, c5 = st.columns(3)
        c1.metric("Total Invested", f"${fmt(invested)}")
        c2.metric("Gross Exit Value", f"${fmt(exit_val)}")
        c3.metric("MOIC", f"{fmt(moic)}x")
        c4.metric("IRR", f"{fmt(fund_irr * 100)}%" if fund_irr == fund_irr else "N/A")
        c5.metric("Total Deals", f"{len(df)}")
        
# ------------------ AGGREGATED EXITS ------------------
with tabs[3]:
    st.subheader("Aggregated Exit Scenarios")

    if not df.empty:
        # 1. Setup Constants & Base Calculations
        total_invested = df.invested.sum()
        base_gev = df["Exit Value"].sum()
        
        # Calculate fees based on your Admin Fee logic
        admin_cost_val = (admin_cost / 100) * target_fund
        total_fees = (admin_cost_val * investment_period) + admin_cost_val

        st.metric("Total Invested Capital", f"${fmt(total_invested)}")

        # 2. Define Scenarios with Bold Markdown formatting
        # We use ** to make them bold in the column headers
        scenarios = ["**Base Case**", "**Upside Case**", "**High Growth Case**"]
        multipliers = [1.0, 1.5, 2.0]
        
        data = []

        for scenario_name, mult in zip(scenarios, multipliers):
            gev = base_gev * mult
            profit_before_carry = gev - total_invested
            gross_moic = gev / total_invested if total_invested > 0 else 0
            
            # Carry Tier Logic
            if gross_moic < t2_exp_moic:
                carry_pct = tier1_carry
            elif gross_moic < t3_exp_moic:
                carry_pct = tier2_carry
            else:
                carry_pct = tier3_carry
            
            carry_amt = max(0, profit_before_carry * (carry_pct / 100))
            net_to_investors = gev - carry_amt - total_fees
            real_moic = net_to_investors / total_invested if total_invested > 0 else 0
            scenario_irr = irr(real_moic, exit_horizon)

            data.append({
                "Scenario": scenario_name,
                "GEV": gev,
                "Profit Before Carry": profit_before_carry,
                "Gross MOIC": gross_moic,
                "Carry %": carry_pct,
                "Carry Amount": carry_amt,
                "Total Fees": total_fees,
                "Net to Investors": net_to_investors,
                "Real MOIC": real_moic,
                "IRR": scenario_irr
            })

        # 3. Transform Data for Display
        metrics_labels = [
            ("Gross Exit Value", "GEV", "${}"),
            ("Profit Before Carry", "Profit Before Carry", "${}"),
            ("Gross MOIC", "Gross MOIC", "{}x"),
            ("Carry (%)", "Carry %", "{}%"),
            ("Carry Amount", "Carry Amount", "${}"),
            ("Total Fees", "Total Fees", "${}"),
            ("Net to Investors", "Net to Investors", "${}"),
            ("Real MOIC to Investors", "Real MOIC", "{}x"),
            ("IRR", "IRR", "{}%")
        ]

        final_rows = []
        for label, key, format_str in metrics_labels:
            row = {"**Metric**": label} # Bold the metric column header too
            for entry in data:
                # Use the bolded scenario name as the key
                s_name = entry["Scenario"]
                val = entry[key]
                
                if "%" in format_str:
                    row[s_name] = f"{fmt(val * 100 if key == 'IRR' else val)}%"
                elif "x" in format_str:
                    row[s_name] = f"{fmt(val)}x"
                else:
                    row[s_name] = f"${fmt(val)}"
            final_rows.append(row)

        exits_df = pd.DataFrame(final_rows)
        
        # 4. Use st.table for a static, clean "financial report" look
        # st.table respects the Markdown bolding in the column headers
        st.table(exits_df.set_index("**Metric**"))
        
    else:
        st.info("Please add deals in the 'Deal Prognosis' tab to see aggregated exits.")

    # 6. Combined Scenario Analysis Graph
    st.divider()
    st.subheader("Scenario Comparison")
        
    scenario_labels = [d["Scenario"].replace("**", "") for d in data]
    gevs = [d["GEV"] for d in data]
    invested_vals = [total_invested] * 3
    irrs = [d["IRR"] * 100 for d in data] # Convert to percentage

    fig6 = go.Figure()
    # Columns for Investment and GEV
    fig6.add_trace(go.Bar(x=scenario_labels, y=invested_vals, name="Invested Capital", marker_color='lightslategray'))
    fig6.add_trace(go.Bar(x=scenario_labels, y=gevs, name="Gross Exit Value", marker_color='royalblue'))
    
    # Line for IRR
    fig6.add_trace(go.Scatter(x=scenario_labels, y=irrs, name="IRR (%)", yaxis='y2', 
                              line=dict(color='firebrick', width=4), mode='lines+markers+text',
                              text=[f"{v:.1f}%" for v in irrs], textposition="top center"))
    fig6.update_layout(
        title="Scenario Outcome: Capital vs. Returns",
        yaxis=dict(title="Amount ($)"),
        yaxis2=dict(title="IRR (%)", overlaying='y', side='right', range=[0, max(irrs)*1.2 if irrs else 100]),
        barmode='group',
        legend=dict(orientation="h", y=-0.2)
    )
    st.plotly_chart(fig6, use_container_width=True)
    

# ------------------ ADMIN FEE ------------------
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
