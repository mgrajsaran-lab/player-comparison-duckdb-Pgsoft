import sys
from comparison_engine import (
    run_comparison as run_engine,
    build_engine
)
import os
import zipfile
import duckdb

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QCheckBox,
    QMessageBox
)
MAX_EXCEL_ROWS = 900_000


def export_dataframe(df, folder, base_name):

    if len(df) <= MAX_EXCEL_ROWS:

        csv_path = os.path.join(
            folder,
            f"{base_name}.csv"
        )

        df.to_csv(
            csv_path,
            index=False
        )

        return csv_path

    zip_path = os.path.join(
        folder,
        f"{base_name}_split.zip"
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED
    ) as z:

        for i, start in enumerate(
            range(0, len(df), MAX_EXCEL_ROWS),
            start=1
        ):

            part = df.iloc[
                start:start + MAX_EXCEL_ROWS
            ]

            csv_name = (
                f"{base_name}_part{i}.csv"
            )

            temp_csv = os.path.join(
                folder,
                csv_name
            )

            part.to_csv(
                temp_csv,
                index=False
            )

            z.write(
                temp_csv,
                csv_name
            )

            os.remove(temp_csv)

    return zip_path

class PlayerComparisonUI(QWidget):

    def __init__(self):
        super().__init__()

        self.bo_file = ""
        self.admin_file = ""
        self.result = None

        self.setWindowTitle("Player Comparison")
        self.resize(700, 450)

        layout = QVBoxLayout()

        self.bo_label = QLabel("BO File: Not Selected")
        self.admin_label = QLabel("Admin File: Not Selected")

        btn_bo = QPushButton("Browse BO Parquet")
        btn_admin = QPushButton("Browse Admin Parquet")

        btn_bo.clicked.connect(self.select_bo)
        btn_admin.clicked.connect(self.select_admin)

        self.chk_admin = QCheckBox("Multiply Admin totals by 1000")
        self.chk_bo = QCheckBox("Multiply BO totals by 1000")

        self.run_btn = QPushButton("Run Comparison")
        self.run_btn.clicked.connect(self.run_comparison)

        self.export_variance_btn = QPushButton("Export Variance CSV")
        self.export_variance_btn.clicked.connect(
            self.export_variance
        )

        self.export_admin_btn = QPushButton(
            "Export Missing Admin CSV"
        )
        self.export_admin_btn.clicked.connect(
            self.export_missing_admin
        )

        self.export_bo_btn = QPushButton(
            "Export Missing BO CSV"
        )
        self.export_bo_btn.clicked.connect(
            self.export_missing_bo
        )

        layout.addWidget(self.bo_label)
        layout.addWidget(btn_bo)

        layout.addWidget(self.admin_label)
        layout.addWidget(btn_admin)

        layout.addWidget(self.chk_admin)
        layout.addWidget(self.chk_bo)

        layout.addWidget(self.run_btn)

        layout.addWidget(self.export_variance_btn)
        layout.addWidget(self.export_admin_btn)
        layout.addWidget(self.export_bo_btn)

        self.setLayout(layout)
    def select_bo(self):

        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select BO Parquet",
            "",
            "Parquet Files (*.parquet)"
        )

        if file_name:
            self.bo_file = file_name
            self.bo_label.setText(
                f"BO File: {file_name}"
            )

    def select_admin(self):

        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select Admin Parquet",
            "",
            "Parquet Files (*.parquet)"
        )

        if file_name:
            self.admin_file = file_name
            self.admin_label.setText(
                f"Admin File: {file_name}"
            )

    def run_comparison(self):

        if not self.bo_file:
            QMessageBox.warning(
                self,
                "Missing File",
                "Select BO parquet file"
            )
            return

        if not self.admin_file:
            QMessageBox.warning(
                self,
                "Missing File",
                "Select Admin parquet file"
            )
            return

        try:

            self.result = run_engine(
                self.bo_file,
                self.admin_file,
                multiply_bo=self.chk_bo.isChecked(),
                multiply_admin=self.chk_admin.isChecked()
            )

            summary = self.result["summary"]

            QMessageBox.information(
                self,
                "Comparison Complete",
                f"""
Total Players : {summary['merged_rows']}

Variance Rows : {summary['variance_rows']}

Missing In Admin : {summary['missing_in_admin']}

Missing In BO : {summary['missing_in_bo']}
"""
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Error",
                str(e)
            )

    def export_variance(self):

        if not self.result:
            QMessageBox.warning(
                self,
                "Run First",
                "Run comparison first"
            )
            return

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder"
        )

        if not folder:
            return

        csv_path = os.path.join(
            folder,
            "variance.csv"
        )

        try:

            con = build_engine(
                self.result["bo_parquet"],
                self.result["admin_parquet"],
                self.result["multiply_bo"],
                self.result["multiply_admin"]
            )

            df = con.execute("""
                
                    SELECT *
                    FROM variance
                """).fetchdf()
            output_file = export_dataframe(
                df,
                folder,
                "variance"
            )


            con.close()

            QMessageBox.information(
                self,
                "Export Complete",
                f"Variance exported successfully.\n\n{output_file}"
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Export Error",
                str(e)
            )

    def export_missing_admin(self):

        if not self.result:
            QMessageBox.warning(
                self,
                "Run First",
                "Run comparison first"
            )
            return

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder"
        )

        if not folder:
            return

        csv_path = os.path.join(
            folder,
            "missing_in_admin.csv"
        )

        try:

            con = build_engine(
                self.result["bo_parquet"],
                self.result["admin_parquet"],
                self.result["multiply_bo"],
                self.result["multiply_admin"]
            )

            df = con.execute("""
                
                    SELECT *
                    FROM merged
                    WHERE Bet_BO <> 0
                    AND Bet_Admin = 0
                """).fetchdf()
            output_file = export_dataframe(
                        df,
                        folder,
                        "missing_in_admin"
                             )
            

            con.close()

            QMessageBox.information(
                self,
                "Export Complete",
                f"Missing Admin exported successfully.\n\n{output_file}"
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Export Error",
                str(e)
            )

    def export_missing_bo(self):

        if not self.result:
            QMessageBox.warning(
                self,
                "Run First",
                "Run comparison first"
            )
            return

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder"
        )

        if not folder:
            return

        csv_path = os.path.join(
            folder,
            "missing_in_bo.csv"
        )

        try:

            con = build_engine(
                self.result["bo_parquet"],
                self.result["admin_parquet"],
                self.result["multiply_bo"],
                self.result["multiply_admin"]
            )

            df = con.execute("""
                
                    SELECT *
                    FROM merged
                    WHERE Bet_Admin <> 0
                    AND Bet_BO = 0
                """).fetchdf()
            output_file = export_dataframe(
                    df,
                    folder,
                    "missing_in_bo"
                )
            

            con.close()

            QMessageBox.information(
                self,
                "Export Complete",
                f"Missing BO exported successfully.\n\n{output_file}"
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Export Error",
                str(e)
            )
    
if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = PlayerComparisonUI()
    window.show()

    sys.exit(app.exec())
