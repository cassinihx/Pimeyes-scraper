import sys, os, json, subprocess, datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QTextEdit, QFileDialog,
    QVBoxLayout, QMessageBox, QDialog, QSpinBox, QLineEdit, QCheckBox, QFormLayout, QHBoxLayout
)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer

RUN_SCRIPT   = "run_automations.py"
CONFIG_FILE  = "config.json"
LOG_DIR      = "logs"
IMAGE_PATH   = os.path.join("Source_Images", "Webcam_Capture.jpg")

class ConfigDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")

        # ---------- provider switches ----------
        self.chk_pimeyes = QCheckBox("Enable PimEyes search")
        self.chk_facechk = QCheckBox("Enable FaceCheck search")

        prov = cfg.get("providers", {})
        self.chk_pimeyes.setChecked(prov.get("pimeyes",  {}).get("enabled", True))
        self.chk_facechk.setChecked(prov.get("facecheck", {}).get("enabled", True))

        # ---------- existing fields -------------
        self.spin_cam   = QSpinBox(); self.spin_cam.setRange(0, 9)
        self.line_token = QLineEdit(); self.line_token.setMinimumWidth(260)
        self.chk_test   = QCheckBox("Use FaceCheck testing mode (free / slow)")

        self.spin_cam.setValue(cfg.get("webcam_index", 0))
        self.line_token.setText(prov.get("facecheck", {}).get("api_token", ""))
        self.chk_test.setChecked(prov.get("facecheck", {}).get("testing_mode", True))

        # ---------- layout ----------
        form = QFormLayout()
        form.addRow(self.chk_pimeyes)           # make check-boxes visible
        form.addRow(self.chk_facechk)

        form.addRow("Webcam index:", self.spin_cam)
        form.addRow("FaceCheck API token:", self.line_token)
        form.addRow("", self.chk_test)

        btn_ok = QPushButton("Save"); btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept); btn_cancel.clicked.connect(self.reject)
        h = QHBoxLayout(); h.addWidget(btn_ok); h.addWidget(btn_cancel)
        form.addRow(h)

        self.setLayout(form)

    def values(self):
        return {
            "webcam_index": self.spin_cam.value(),
            "providers": {
                "pimeyes":  { "enabled": self.chk_pimeyes.isChecked() },
                "facecheck": {
                    "enabled":     self.chk_facechk.isChecked(),
                    "api_token":   self.line_token.text().strip(),
                    "testing_mode": self.chk_test.isChecked()
                }
            }
        }


class Worker(QThread):
    out = pyqtSignal(str)
    err = pyqtSignal(str)
    done = pyqtSignal()

    def run(self):
        if not os.path.exists(RUN_SCRIPT):
            self.err.emit(f"ERROR: {RUN_SCRIPT} not found")
            return
        proc = subprocess.Popen([
            sys.executable, RUN_SCRIPT
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           text=True, encoding="utf-8", bufsize=1)
        for line in proc.stdout:
            self.out.emit(line.rstrip())
        proc.wait(); self.done.emit()

class AutomationUI(QWidget):
    def __init__(self):
        super().__init__()
        # keep window above Chrome
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.build_ui()

    # ---------------- UI LAYOUT ----------------
    def build_ui(self):
        self.setWindowTitle("PimEyes Automation UI")
        self.resize(900, 800)

        self.btn_run   = QPushButton("Run Automation")
        self.btn_edit  = QPushButton("Edit Config")
        self.btn_logs  = QPushButton("View Logs")
        self.btn_run.clicked.connect(self.start_automation)
        self.btn_edit.clicked.connect(self.edit_config)
        self.btn_logs.clicked.connect(self.view_logs)

        self.result_label  = QLabel("Search Results URL:")
        self.result_box    = QTextEdit(readOnly=True)
        self.log_box       = QTextEdit(readOnly=True)
        self.image_label   = QLabel("Picture will appear here")
        self.image_label.setFixedSize(512, 384)
        self.image_label.setStyleSheet("border:1px solid black")

        self.status_label = QLabel("Waiting …")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("Courier", 14, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color:gray;border:2px solid gray;padding:4px")

        lay = QVBoxLayout(self)
        lay.addWidget(self.btn_run); lay.addWidget(self.btn_edit); lay.addWidget(self.btn_logs)
        lay.addWidget(self.image_label); lay.addWidget(self.status_label)
        lay.addWidget(self.result_label); lay.addWidget(self.result_box)
        lay.addWidget(QLabel("Logs:")); lay.addWidget(self.log_box)

        # searching animation timer
        self.timer = QTimer(); self.timer.timeout.connect(self.tick)
        self.dots = 0

    # ---------------- slots ----------------
    def start_automation(self):
        self.log_box.clear(); self.result_box.clear();
        self.status_label.setText("Searching"); self.status_label.setStyleSheet("color:lime;border:2px solid lime;padding:4px")
        self.timer.start(500)
        # clears old image
        self.image_label.clear()

        self.thread = Worker()
        self.thread.out.connect(self.handle_output)
        self.thread.err.connect(self.handle_output)
        self.thread.done.connect(self.finish)
        self.thread.start()

    def handle_output(self, line:str):
        self.log_box.append(line)
        if line == "SNAP_COMPLETE":
            self.refresh_image()
        if "Search Results URL:" in line:
            url = line.split("Search Results URL:")[-1].strip()
            self.result_box.setPlainText(url)
            self.status_label.setText("Search Complete")
            self.timer.stop()

        if line.startswith("FACECHECK_MATCH"):
            _, score, url = line.split(maxsplit=2)
            self.result_box.append(f"FaceCheck {score}%  {url}")

        if "Search Results URL:" in line:           # PimEyes line
            url = line.split("Search Results URL:")[-1].strip()
            self.result_box.append(f"PimEyes   {url}")
            self.status_label.setText("Search Complete")
            self.timer.stop()


    def finish(self):
        if self.timer.isActive():
            self.timer.stop(); self.status_label.setText("Finished")

    def tick(self):
        self.dots = (self.dots+1)%4
        self.status_label.setText("Searching"+"."*self.dots)

    def refresh_image(self):
        if os.path.exists(IMAGE_PATH):
            pix = QPixmap(IMAGE_PATH)
            self.image_label.setPixmap(pix.scaled(512,384, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.image_label.setText("Image not found")

    # ---------- config & log helpers ----------
    def edit_config(self):
        cfg = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except json.JSONDecodeError:
                QMessageBox.warning(self, "Error", "Config file is corrupted; loading defaults.")

        dlg = ConfigDialog(cfg, self)
        if dlg.exec():
            new_cfg = dlg.values()
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(new_cfg, f, indent=2)
            QMessageBox.information(self, "Saved", "Settings updated.")


    def view_logs(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select log", LOG_DIR, "Text Files (*.txt)")
        if file:
            with open(file, "r", encoding="utf-8") as f:
                self.log_box.setPlainText(f.read())

    def get_editor(self, title, default=""):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
        dlg = QDialog(self); dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        te = QTextEdit(); te.setPlainText(default)
        lay.addWidget(te)
        btn_ok = QPushButton("Save"); btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(lambda: dlg.done(1)); btn_cancel.clicked.connect(lambda: dlg.done(0))
        lay.addWidget(btn_ok); lay.addWidget(btn_cancel)
        dlg.setLayout(lay)
        if dlg.exec():
            return te.toPlainText(), True
        return "", False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = AutomationUI()
    w.showMaximized()
    sys.exit(app.exec())
