import streamlit as st
import pandas as pd
from datetime import date, datetime
from sqlalchemy import create_engine, text
from dateutil.relativedelta import relativedelta
import plotly.express as px
import os

# ---------- DB SETUP ----------
DB_URL = "sqlite:///expenses.db"
engine = create_engine(DB_URL, future=True)

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                amount REAL NOT NULL
            )
        """))
        # Optional indexes for faster queries
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_expenses_cat ON expenses(category)"))

def insert_expense(exp_date: str, category: str, description: str, amount: float):
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO expenses (date, category, description, amount) VALUES (:d, :c, :desc, :a)"),
            {"d": exp_date, "c": category, "desc": description, "a": amount}
        )

def fetch_df():
    if not os.path.exists("expenses.db"):
        return pd.DataFrame(columns=["id","date","category","description","amount"])
    df = pd.read_sql("SELECT * FROM expenses ORDER BY date DESC, id DESC", engine)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

def bulk_insert(df_csv: pd.DataFrame):
    # Expect columns: date,category,description,amount
    # date as yyyy-mm-dd
    if "date" in df_csv.columns:
        df_csv["date"] = pd.to_datetime(df_csv["date"]).dt.date.astype(str)
    df_csv.to_sql("expenses", engine, if_exists="append", index=False)

def delete_expense(exp_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM expenses WHERE id=:id"), {"id": exp_id})

def clear_all_expenses():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM expenses"))

# ---------- APP UI ----------
st.set_page_config(page_title="Personal Expense Tracker", page_icon="💰", layout="wide")
st.title("💰 Personal Expense Tracker")

init_db()

with st.sidebar:
    st.header("➕ Add Expense")
    exp_date = st.date_input("Date", date.today())
    categories = ["Food", "Transport", "Bills", "Shopping", "Entertainment", "Health", "Education", "Other"]
    category = st.selectbox("Category", categories)
    description = st.text_input("Description")
    amount = st.number_input("Amount", min_value=0.0, format="%.2f")
    if st.button("Add"):
        if amount > 0:
            insert_expense(exp_date.isoformat(), category, description, float(amount))
            st.success("Expense added.")
        else:
            st.warning("Amount must be > 0.")

    st.divider()
    st.header("⬆️ Import CSV")
    st.caption("Columns required: date (YYYY-MM-DD), category, description, amount")
    file = st.file_uploader("Choose CSV", type=["csv"])
    if file is not None:
        try:
            df_csv = pd.read_csv(file)
            assert {"date","category","amount"}.issubset(set(df_csv.columns))
            # Coerce amount
            df_csv["amount"] = pd.to_numeric(df_csv["amount"], errors="coerce").fillna(0.0)
            df_csv = df_csv[df_csv["amount"] > 0]
            bulk_insert(df_csv[["date","category","description","amount"]])
            st.success(f"Imported {len(df_csv)} rows.")
        except Exception as e:
            st.error(f"Import failed: {e}")

    st.divider()
    st.header("🎯 Monthly Budget")
    monthly_budget = st.number_input("Set monthly budget (₹)", min_value=0.0, value=0.0, step=100.0)

df = fetch_df()

tab1, tab2, tab3, tab4 = st.tabs(["📋 Table", "📊 Category Summary", "📈 Trends", "📦 Export"])

with tab1:
    st.subheader("All Expenses")
    if df.empty:
        st.info("No expenses to show.")
    else:
        for i in range(len(df)):
            row = df.iloc[i]
            cols = st.columns([2,2,4,2,1])
            cols[0].write(row["date"])
            cols[1].write(row["category"])
            cols[2].write(row["description"])
            cols[3].write(f"₹{row['amount']:.2f}")
            if cols[4].button("🗑️", key=f"del_{row['id']}"):
                delete_expense(int(row["id"]))
                st.rerun()
        if st.button("🟥 Clear All"):
            clear_all_expenses()
            st.rerun()

with tab2:
    st.subheader("Spend by Category")
    if df.empty:
        st.info("No data yet. Add some expenses.")
    else:
        by_cat = df.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
        c1, c2 = st.columns([3,2])
        with c1:
            fig = px.bar(by_cat, x="category", y="amount", title="Total Spend by Category")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.metric("Total Spend", f"₹{df['amount'].sum():,.2f}")
            if monthly_budget and monthly_budget > 0:
                this_month = pd.Timestamp.today().strftime("%Y-%m")
                month_sum = df[pd.to_datetime(df["date"]).dt.strftime("%Y-%m") == this_month]["amount"].sum()
                st.metric("This Month", f"₹{month_sum:,.2f}")
                diff = monthly_budget - month_sum
                st.metric("Budget Left", f"₹{diff:,.2f}")

with tab3:
    st.subheader("Monthly Trend")
    if df.empty:
        st.info("No data yet. Add some expenses.")
    else:
        dft = df.copy()
        dft["month"] = pd.to_datetime(dft["date"]).values.astype("datetime64[M]")
        by_month = dft.groupby("month", as_index=False)["amount"].sum()
        by_month = by_month.sort_values("month")
        fig2 = px.line(by_month, x="month", y="amount", markers=True, title="Monthly Spend")
        st.plotly_chart(fig2, use_container_width=True)

with tab4:
    st.subheader("Export")
    if df.empty:
        st.info("Nothing to export.")
    else:
        out = df.sort_values(["date","id"], ascending=[False, False]).copy()
        out["date"] = out["date"].astype(str)
        csv = out.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv, file_name="expenses_export.csv", mime="text/csv")
