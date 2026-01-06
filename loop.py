import streamlit as st
import sqlite3
import qrcode
from datetime import datetime
import json
import cv2
import io
import pandas as pd
import random
import numpy as np
import string

# -----------------------------
# DATABASE INITIALIZATION
# -----------------------------
def init_db():
    conn = sqlite3.connect("pallets.db", check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        batch_id TEXT PRIMARY KEY,
        product_name TEXT NOT NULL,
        company TEXT NOT NULL,
        level TEXT NOT NULL,
        deadline TEXT,
        stock_percent INTEGER,
        status TEXT,
        last_updated TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transaction_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT,
        operation TEXT,
        quantity_change INTEGER,
        previous_stock INTEGER,
        new_stock INTEGER,
        timestamp TEXT,
        FOREIGN KEY(batch_id) REFERENCES products(batch_id)
    )
    """)

    conn.commit()
    return conn


# -----------------------------
# SESSION STATE
# -----------------------------
if "page" not in st.session_state:
    st.session_state.page = "home"


def navigate_to(page):
    st.session_state.page = page


def back_to_home():
    st.session_state.page = "home"


# -----------------------------
# HOME PAGE
# -----------------------------
def home_page():
    st.title("🏭 Rough Casting Management System")
    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    col1.button("📝 Register New Product", on_click=navigate_to, args=("register",))
    col2.button("📷 Scan QR Code", on_click=navigate_to, args=("scan",))
    col3.button("📊 View Reports", on_click=navigate_to, args=("reports",))

    st.markdown("---")

    conn = init_db()
    df = pd.read_sql("""
        SELECT batch_id, product_name, company, level, status
        FROM products
        ORDER BY last_updated DESC
        LIMIT 5
    """, conn)
    conn.close()

    if df.empty:
        st.info("No products found. Register a new product to get started.")
    else:
        st.subheader("Recently Updated Products")
        st.dataframe(df, hide_index=True, use_container_width=True)


# -----------------------------
# REGISTER PAGE
# -----------------------------
def register_page():
    col1, col2 = st.columns([1, 6])
    col1.button("⬅ Back", on_click=back_to_home)

    st.title("📝 Register New Product")
    st.markdown("---")

    with st.form("register_form"):
        product_name = st.text_input("Product Name")
        company = st.text_input("Company")

        col1, col2 = st.columns(2)
        level = col1.selectbox("Production Level", ["Raw", "Processing", "Finished", "Shipped"])
        deadline = col2.date_input("Deadline")

        stock_percent = st.slider("Initial Stock %", 0, 100, 50)
        submit = st.form_submit_button("Register Product")

    if not submit:
        return

    if not product_name or not company:
        st.error("Product name and company are required.")
        return

    batch_id = (
        f"{company[:3].upper()}-"
        f"{product_name[:3].upper()}-"
        f"{datetime.now().strftime('%y%m%d')}-"
        f"{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    )

    conn = init_db()
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        batch_id,
        product_name,
        company,
        level,
        deadline.strftime("%Y-%m-%d"),
        stock_percent,
        "Pending",
        timestamp
    ))

    conn.commit()
    conn.close()

    qr_data = json.dumps({"batch_id": batch_id})
    img = qrcode.make(qr_data)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    st.success(f"Product registered successfully! Batch ID: {batch_id}")
    st.image(buf, width=200)
    st.download_button("Download QR Code", buf, f"{batch_id}.png", "image/png")


# -----------------------------
# SCAN PAGE (OpenCV QR Decoder)
# -----------------------------
def scan_page():
    col1, col2 = st.columns([1, 6])
    col1.button("⬅ Back", on_click=back_to_home)

    st.title("📷 Scan QR Code")
    st.markdown("---")

    uploaded = st.file_uploader("Upload QR Code", ["png", "jpg", "jpeg"])

    if not uploaded:
        return

    img = cv2.imdecode(np.frombuffer(uploaded.getvalue(), np.uint8), cv2.IMREAD_COLOR)

    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(img)

    if not data:
        st.error("No QR code detected.")
        return

    qr_data = json.loads(data)
    batch_id = qr_data.get("batch_id")

    conn = init_db()
    product = pd.read_sql(
        "SELECT * FROM products WHERE batch_id = ?",
        conn,
        params=(batch_id,)
    )

    if product.empty:
        st.error("Product not found in database.")
        conn.close()
        return

    st.subheader("Product Details")
    st.dataframe(product.drop(columns=["last_updated"]), hide_index=True)

    current_stock = int(product.iloc[0]["stock_percent"])

    with st.form("update_stock"):
        change = st.number_input("Stock Change (%)", -100, 100, 0)
        update = st.form_submit_button("Update Stock")

    if update:
        new_stock = current_stock + change
        if not 0 <= new_stock <= 100:
            st.error("Stock must be between 0 and 100.")
        else:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE products SET stock_percent=?, last_updated=?
                WHERE batch_id=?
            """, (new_stock, ts, batch_id))

            cursor.execute("""
                INSERT INTO transaction_logs
                (batch_id, operation, quantity_change, previous_stock, new_stock, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (batch_id, "Stock Update", change, current_stock, new_stock, ts))

            conn.commit()
            st.success("Stock updated successfully.")
            st.experimental_rerun()

    conn.close()


# -----------------------------
# REPORTS PAGE
# -----------------------------
def reports_page():
    col1, col2 = st.columns([1, 6])
    col1.button("⬅ Back", on_click=back_to_home)

    st.title("📊 Product Reports")
    st.markdown("---")

    conn = init_db()
    df = pd.read_sql("SELECT * FROM products ORDER BY deadline", conn)
    conn.close()

    if df.empty:
        st.info("No data available.")
        return

    st.dataframe(df.drop(columns=["last_updated"]), use_container_width=True)

    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode(),
        "products_report.csv",
        "text/csv"
    )


# -----------------------------
# MAIN
# -----------------------------
def main():
    st.set_page_config(
        page_title="Rough Casting Management",
        page_icon="🏭",
        layout="wide"
    )

    if st.session_state.page == "home":
        home_page()
    elif st.session_state.page == "register":
        register_page()
    elif st.session_state.page == "scan":
        scan_page()
    elif st.session_state.page == "reports":
        reports_page()


if __name__ == "__main__":
    main()
