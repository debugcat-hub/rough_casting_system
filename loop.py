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
import hashlib

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
        timestamp TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash TEXT,
        role TEXT
    )
    """)

    # default admin
    admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
    cursor.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
        ("admin", admin_hash, "admin")
    )

    conn.commit()
    return conn


# -----------------------------
# SESSION STATE
# -----------------------------
if "page" not in st.session_state:
    st.session_state.page = "login"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = None


def go(page):
    st.session_state.page = page


def logout():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.page = "login"


# -----------------------------
# LOGIN PAGE
# -----------------------------
def login_page():
    st.title("🔐 Login – Rough Casting System")
    st.markdown("---")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

    st.markdown("New user?")
    st.button("🆕 Create Account", on_click=go, args=("register_user",))

    if not submit:
        return

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    conn = init_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE username=? AND password_hash=?",
        (username, password_hash)
    )
    user = cursor.fetchone()
    conn.close()

    if user:
        st.session_state.logged_in = True
        st.session_state.username = username
        st.session_state.page = "home"
        st.experimental_rerun()
    else:
        st.error("Invalid username or password")


# -----------------------------
# REGISTER USER PAGE
# -----------------------------
def register_user_page():
    st.title("🆕 Create New Account")
    st.markdown("---")

    with st.form("register_user_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")
        submit = st.form_submit_button("Register")

    st.button("⬅ Back to Login", on_click=go, args=("login",))

    if not submit:
        return

    if not username or not password:
        st.error("All fields are required")
        return

    if password != confirm:
        st.error("Passwords do not match")
        return

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    conn = init_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO users VALUES (?, ?, ?)",
            (username, password_hash, "operator")
        )
        conn.commit()
        st.success("Account created! You can now log in.")
        st.session_state.page = "login"
        st.experimental_rerun()
    except sqlite3.IntegrityError:
        st.error("Username already exists")
    finally:
        conn.close()


# -----------------------------
# HOME PAGE
# -----------------------------
def home_page():
    st.title("🏭 Rough Casting Management System")

    col1, col2 = st.columns([5, 1])
    col2.button("🚪 Logout", on_click=logout)

    st.markdown("---")

    c1, c2, c3 = st.columns(3)
    c1.button("📝 Register Product", on_click=go, args=("register_product",))
    c2.button("📷 Scan QR", on_click=go, args=("scan",))
    c3.button("📊 Reports", on_click=go, args=("reports",))


# -----------------------------
# REGISTER PRODUCT
# -----------------------------
def register_product_page():
    st.button("⬅ Back", on_click=go, args=("home",))
    st.title("📝 Register Product")
    st.markdown("---")

    with st.form("product_form"):
        product_name = st.text_input("Product Name")
        company = st.text_input("Company")
        level = st.selectbox("Level", ["Raw", "Processing", "Finished", "Shipped"])
        deadline = st.date_input("Deadline")
        stock_percent = st.slider("Stock %", 0, 100, 50)
        submit = st.form_submit_button("Register")

    if not submit:
        return

    batch_id = (
        f"{company[:3].upper()}-"
        f"{product_name[:3].upper()}-"
        f"{datetime.now().strftime('%y%m%d')}-"
        f"{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    )

    conn = init_db()
    conn.execute(
        "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            batch_id,
            product_name,
            company,
            level,
            deadline.strftime("%Y-%m-%d"),
            stock_percent,
            "Pending",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()

    qr = qrcode.make(json.dumps({"batch_id": batch_id}))
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)

    st.success(f"Product registered: {batch_id}")
    st.image(buf, width=200)
    st.download_button("Download QR", buf, f"{batch_id}.png", "image/png")


# -----------------------------
# SCAN PAGE (OpenCV)
# -----------------------------
def scan_page():
    st.button("⬅ Back", on_click=go, args=("home",))
    st.title("📷 Scan QR Code")
    st.markdown("---")

    uploaded = st.file_uploader("Upload QR Image", ["png", "jpg", "jpeg"])
    if not uploaded:
        return

    img = cv2.imdecode(np.frombuffer(uploaded.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)

    if not data:
        st.error("No QR detected")
        return

    batch_id = json.loads(data)["batch_id"]

    conn = init_db()
    df = pd.read_sql("SELECT * FROM products WHERE batch_id=?", conn, params=(batch_id,))
    conn.close()

    if df.empty:
        st.error("Product not found")
        return

    st.dataframe(df.drop(columns=["last_updated"]), hide_index=True)


# -----------------------------
# REPORTS PAGE
# -----------------------------
def reports_page():
    st.button("⬅ Back", on_click=go, args=("home",))
    st.title("📊 Reports")
    st.markdown("---")

    conn = init_db()
    df = pd.read_sql("SELECT * FROM products ORDER BY deadline", conn)
    conn.close()

    st.dataframe(df.drop(columns=["last_updated"]), use_container_width=True)
    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode(),
        "products_report.csv",
        "text/csv",
    )


# -----------------------------
# MAIN
# -----------------------------
def main():
    st.set_page_config("Rough Casting Management", "🏭", layout="wide")
    init_db()

    if not st.session_state.logged_in:
        if st.session_state.page == "register_user":
            register_user_page()
        else:
            login_page()
        return

    if st.session_state.page == "home":
        home_page()
    elif st.session_state.page == "register_product":
        register_product_page()
    elif st.session_state.page == "scan":
        scan_page()
    elif st.session_state.page == "reports":
        reports_page()


if __name__ == "__main__":
    main()
