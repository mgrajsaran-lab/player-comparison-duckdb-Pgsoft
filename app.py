# app.py
# FINAL DuckDB VERSION — FIXED USERID ISSUE

import re
import io
import zipfile
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq
import streamlit as st
import time

# ================= CONFIG =================


EPS = 0.01
MAX_EXCEL_ROWS = 900_000
MAX_PREVIEW_ROWS = 1000

# ================= STREAMLIT =================
st.set_page_config(page_title="Player Comparison — DuckDB", layout="wide")
st.title("🧮 Player Comparison — DuckDB powered")

# ======= MULTIPLIER OPTIONS =======
c1, c2 = st.columns(2)

with c1:
    MULTIPLY_ADMIN = st.checkbox("Multiply Admin totals by 1000", value=False)

with c2:
    MULTIPLY_BO = st.checkbox("Multiply BO totals by 1000", value=False)

ADMIN_MUL = 1000 if MULTIPLY_ADMIN else 1
BO_MUL = 1000 if MULTIPLY_BO else 1
# ================= FILE UPLOADS =================
bo_parquet_upload = st.file_uploader(
    "Upload BO combined.parquet",
    type=["parquet"]
)

admin_parquet_upload = st.file_uploader(
    "Upload Admin combined.parquet",
    type=["parquet"]
)

# ================= UTILS =================
def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def find_col_strict(cols, names, exclude=None):
    exclude = exclude or []
    want = {norm(x) for x in names}

    for c in cols:
        if norm(c) in want and not any(e.lower() in c.lower() for e in exclude):
            return c

    return None

def make_download_asset(df: pd.DataFrame, base_name: str):

    if len(df) <= MAX_EXCEL_ROWS:
        return (
            df.to_csv(index=False).encode(),
            f"{base_name}.csv",
            "text/csv"
        )

    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:

        for i, start in enumerate(range(0, len(df), MAX_EXCEL_ROWS), 1):

            part = df.iloc[start:start + MAX_EXCEL_ROWS]

            z.writestr(
                f"{base_name}_part{i}.csv",
                part.to_csv(index=False)
            )

    buf.seek(0)

    return (
        buf.read(),
        f"{base_name}_split.zip",
        "application/zip"
    )



def parquet_columns(path: Path):
    return pq.ParquetFile(path).schema.names

# ================= BUTTONS =================
c1, c2 = st.columns(2)

with c1:
    run_clicked = st.button(
        "Run comparison (DuckDB)",
        type="primary"
    )

with c2:
    if st.button("🗑️ Clear All"):

        try:
            Path("bo_combined.parquet").unlink(
                missing_ok=True
            )

            Path("admin_combined.parquet").unlink(
                missing_ok=True
            )

        except:
            pass

        st.session_state.clear()

        st.rerun()

# ================= RUN =================
if run_clicked:

    start_time = time.time()
    with st.spinner("Running DuckDB comparison…"):

        # ---------- VALIDATE UPLOADS ----------
        if not bo_parquet_upload:
            st.error("❌ Upload BO combined.parquet")
            st.stop()
        if not admin_parquet_upload:
            st.error("❌ Upload Admin combined.parquet")
            st.stop()
        bo_parquet = "bo_combined.parquet"
        ad_parquet = "admin_combined.parquet"
        with open(bo_parquet, "wb") as f:
            f.write(bo_parquet_upload.getbuffer())
        with open(ad_parquet, "wb") as f:
            f.write(admin_parquet_upload.getbuffer())
        st.write(
            f"Upload Save Time: {time.time() - start_time:.2f}s"
             )

        

        # ---------- GET COLUMNS ----------
        bo_cols = parquet_columns(bo_parquet)
        ad_cols = parquet_columns(ad_parquet)

        # ---------- BO COLUMNS ----------
        bo_key = find_col_strict(bo_cols, ["Player"])
        bo_bet = find_col_strict(bo_cols, ["Stakes"])
        bo_win = find_col_strict(
            bo_cols,
            ["Player W/L"],
            ["%", "percent"]
        )

        # FIXED HERE
        bo_userid = find_col_strict(bo_cols, ["Player"])

        # ---------- ADMIN COLUMNS ----------
        ad_key = find_col_strict(ad_cols, ["Agent Id"])

        ad_bet = find_col_strict(ad_cols, ["Turnover"])

        ad_win = find_col_strict(
            ad_cols,
            ["Member winlose", "Member winloss"],
            ["%", "percent"]
        )

        ad_refid = find_col_strict(ad_cols, ["Own Ref ID"])

        # ---------- VALIDATION ----------
        if not all([
            bo_key,
            bo_bet,
            bo_win,
            bo_userid,
            ad_key,
            ad_bet,
            ad_win,
            
        ]):
            st.error("❌ Required columns not found. Check source files.")
            st.write("BO Columns:", bo_cols)
            st.write("ADMIN Columns:", ad_cols)
            st.stop()

        # ---------- DUCKDB ----------
        con = duckdb.connect()
        
        st.write(
            "BO rows:",
            con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{bo_parquet}')"
                ).fetchone()[0]
        )
        st.write(
            "Admin rows:",
            con.execute(
                 f"SELECT COUNT(*) FROM read_parquet('{ad_parquet}')"
                 ).fetchone()[0]
        )
        if ad_refid:
            own_ref_sql = f'MAX("{ad_refid}") AS OwnRefID,'
        else:
            own_ref_sql = "NULL AS OwnRefID,"
        

        # ================= BO VIEW =================
        con.execute(f"""
            CREATE OR REPLACE TEMP VIEW bo AS

            SELECT
                TRIM("{bo_key}") AS Key,

                MAX("{bo_userid}") AS UserID,

                SUM(
                    CAST(
                        regexp_replace(
                            "{bo_bet}",
                            '[^0-9.-]',
                            '',
                            'g'
                        ) AS DOUBLE
                    )
                ) * {BO_MUL} AS Bet_BO,

                SUM(
                    CAST(
                        regexp_replace(
                            "{bo_win}",
                            '[^0-9.-]',
                            '',
                            'g'
                        ) AS DOUBLE
                    )
                ) * {BO_MUL} AS WinLoss_BO

            FROM read_parquet('{bo_parquet}')

            GROUP BY Key
        """)
        st.write(
            f"BO View Time: {time.time() - start_time:.2f}s"
             )


    # ================= ADMIN VIEW =================
        con.execute(f"""
            CREATE OR REPLACE TEMP VIEW admin AS

            SELECT
                TRIM("{ad_key}") AS Key,

                {own_ref_sql}

                SUM(
                    CAST(
                        regexp_replace(
                            "{ad_bet}",
                            '[^0-9.-]',
                            '',
                            'g'
                        ) AS DOUBLE
                    )
                ) * {ADMIN_MUL} AS Bet_Admin,

                SUM(
                    CAST(
                        regexp_replace(
                            "{ad_win}",
                            '[^0-9.-]',
                            '',
                            'g'
                        ) AS DOUBLE
                    )
                ) * {ADMIN_MUL} AS WinLoss_Admin

            FROM read_parquet('{ad_parquet}')

            GROUP BY Key
        """)
        st.write(
             f"Admin View Time: {time.time() - start_time:.2f}s"
            )

            # ================= MERGE TABLE =================
        con.execute("""
            CREATE OR REPLACE TEMP TABLE merged AS

            SELECT
                COALESCE(b.Key, a.Key) AS Key,

                a.OwnRefID AS "own ref id",

                b.UserID AS "user id",

                COALESCE(b.Bet_BO, 0) AS Bet_BO,

                COALESCE(b.WinLoss_BO, 0) AS WinLoss_BO,

                COALESCE(a.Bet_Admin, 0) AS Bet_Admin,

                COALESCE(a.WinLoss_Admin, 0) AS WinLoss_Admin,

                ROUND(
                    COALESCE(b.Bet_BO, 0)
                    -
                    COALESCE(a.Bet_Admin, 0),
                    2
                ) AS Bet_Diff,

                ROUND(
                    COALESCE(b.WinLoss_BO, 0)
                    -
                    COALESCE(a.WinLoss_Admin, 0),
                    2
                ) AS WinLoss_Diff

            FROM bo b

            FULL OUTER JOIN admin a
            ON b.Key = a.Key
        """)

        merged_rows = con.execute("""
            SELECT COUNT(*)
            FROM merged
        """).fetchone()[0]

        st.write("Merged rows:", merged_rows)

        # ================= VARIANCE TABLE =================
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE variance AS

            SELECT *
            FROM merged

            WHERE
                ABS(Bet_Diff) > {EPS}
                OR
                ABS(WinLoss_Diff) > {EPS}
        """)

        variance_rows = con.execute("""
            SELECT COUNT(*)
            FROM variance
        """).fetchone()[0]

        st.write("Variance rows:", variance_rows)

        # ================= PREVIEW ONLY =================
        variance = con.execute(f"""
            SELECT *
            FROM variance
            LIMIT {MAX_PREVIEW_ROWS}
        """).fetchdf()

        # ================= MISSING IN ADMIN =================
        missing_in_admin = con.execute("""
            SELECT
                Key AS Player,
                Bet_BO AS "Bet (BO)",
                WinLoss_BO AS "WinLoss (BO)"
            FROM merged

            WHERE
                Bet_BO <> 0
                AND Bet_Admin = 0
        """).fetchdf()

        # ================= MISSING IN BO =================
        missing_in_bo = con.execute("""
            SELECT
                Key AS Player,
                Bet_Admin AS "Bet (Admin)",
                WinLoss_Admin AS "WinLoss (Admin)"
            FROM merged

            WHERE
                Bet_Admin <> 0
                AND Bet_BO = 0
        """).fetchdf()


    

        # ================= SUMMARY =================
        summary = pd.DataFrame({

            "Metric": [
                "Total unique players (BO ∪ Admin)",
                "Players with differences",
                "Total Bet difference (BO - Admin)",
                "Total WinLoss difference (BO - Admin)",
                "Missing in Admin (present in BO only)",
                "Missing in BO (present in Admin only)",
            ],

            "Value": [
                merged_rows,
                variance_rows,
                variance["Bet_Diff"].sum(),
                variance["WinLoss_Diff"].sum(),
                len(missing_in_admin),
                len(missing_in_bo),
            ]
        })
        
       

        # ================= STORE =================
        st.session_state["res"] = {
            "summary": summary,
            "variance": variance,
            "missing_in_admin": missing_in_admin,
            "missing_in_bo": missing_in_bo,
        }
        try:
            Path(bo_parquet).unlink(missing_ok=True)
            Path(ad_parquet).unlink(missing_ok=True)
        except:
            pass
        

# ================= DISPLAY =================
if "res" in st.session_state:

    r = st.session_state["res"]

    st.subheader("Summary")

    st.dataframe(
        r["summary"],
        use_container_width=True
    )

    st.markdown("### Variance (preview only)")

    st.caption(
        f"Showing first {MAX_PREVIEW_ROWS:,} rows"
    )

    st.dataframe(
        r["variance"].head(MAX_PREVIEW_ROWS),
        use_container_width=True
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        p, n, m = make_download_asset(
            r["variance"],
            "variance"
        )

        st.download_button(
            "⬇️ variance",
            p,
            n,
            m
        )

    with c2:
        p, n, m = make_download_asset(
            r["missing_in_admin"],
            "missing_in_admin"
        )

        st.download_button(
            "⬇️ missing_in_admin",
            p,
            n,
            m
        )

    with c3:
        p, n, m = make_download_asset(
            r["missing_in_bo"],
            "missing_in_bo"
        )

        st.download_button(
            "⬇️ missing_in_bo",
            p,
            n,
            m
        )

    st.markdown("### Missing in Admin (present in BO only)")

    st.dataframe(
        r["missing_in_admin"],
        use_container_width=True
    )

    st.markdown("### Missing in BO (present in Admin only)")

    st.dataframe(
        r["missing_in_bo"],
        use_container_width=True
    )

    st.success("Done — DuckDB powered 🚀")

else:
    st.info("Click Run comparison (DuckDB) to start.")
