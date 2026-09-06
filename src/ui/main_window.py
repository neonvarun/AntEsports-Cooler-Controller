import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QFrame, QSystemTrayIcon, QMenu,
    QApplication, QDialog
)
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QFont, QAction, QColor, QPainter, QPen, QBrush, QIcon, QPixmap
)

from ..config_manager import ConfigManager
from ..cooler_protocol import AntiBlinkMode, DisplayMetric, TemperatureUnit
from ..cooler_service import CoolerService
from ..sensor_engine import is_admin_user, restart_as_admin

ZINC_STYLESHEET = """
QMainWindow {
    background-color: #09090B;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
}

QWidget {
    color: #FAFAFA;
    font-size: 12px;
}

QLabel {
    background-color: transparent;
    border: none;
}

.hero-card {
    background-color: #111115;
    border: 1px solid #27272A;
    border-radius: 12px;
}

.zinc-card {
    background-color: #111115;
    border: 1px solid #27272A;
    border-radius: 10px;
}

.pill-container {
    background-color: #18181B;
    border: 1px solid #27272A;
    border-radius: 8px;
}

QCheckBox {
    color: #A1A1AA;
    spacing: 7px;
    font-size: 11px;
    font-weight: 500;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #3F3F46;
    background-color: #18181B;
}

QCheckBox::indicator:checked {
    background-color: #2563EB;
    border: 1px solid #3B82F6;
}

QPushButton.footer-btn {
    background-color: #18181B;
    border: 1px solid #27272A;
    color: #A1A1AA;
    font-weight: 500;
    font-size: 11px;
    padding: 4px 12px;
    border-radius: 6px;
    min-height: 22px;
}

QPushButton.footer-btn:hover {
    background-color: #27272A;
    color: #FAFAFA;
    border: 1px solid #3F3F46;
}

QMenu {
    background-color: #121217;
    border: 1px solid #27272A;
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    color: #E4E4E7;
    padding: 6px 22px 6px 12px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
}

QMenu::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}

QMenu::item:disabled {
    color: #71717A;
}

QMenu::separator {
    height: 1px;
    background-color: #27272A;
    margin: 4px 6px;
}
"""

class MicroProgressBar(QWidget):
    """Sleek 4px rounded progress indicator for KPI cards."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self.value = 0.0
        self.fill_color = QColor("#3B82F6")

    def setValue(self, val: float, color: QColor = None):
        self.value = max(0.0, min(100.0, val))
        if color:
            self.fill_color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = float(self.width())
        h = float(self.height())
        
        # Background Track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#222227")))
        painter.drawRoundedRect(QRectF(0, 0, w, h), 2, 2)
        
        # Active Progress
        prog_w = (self.value / 100.0) * w
        if prog_w > 0:
            painter.setBrush(QBrush(self.fill_color))
            painter.drawRoundedRect(QRectF(0, 0, max(prog_w, 4.0), h), 2, 2)


class SaaSMetricGauge(QWidget):
    """
    Modern SaaS-grade continuous vector arc HUD.
    Features:
    - Sleek 270° continuous anti-aliased gradient arc with rounded caps
    - Crisp high-contrast tabular readout with dynamic accent unit
    - Muted uppercase metric subtitle with tracking
    - Dynamic emerald anti-blink active pill
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(250, 200)
        self.value = 0
        self.unit = "°C"
        self.metric_label = "CPU TEMPERATURE"
        self.antiblink_active = False

    def set_data(self, val: int, unit: str, label: str, antiblink: bool):
        if self.value != val or self.unit != unit or self.metric_label != label or self.antiblink_active != antiblink:
            self.value = val
            self.unit = unit
            self.metric_label = label
            self.antiblink_active = antiblink
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        cx = self.width() / 2.0
        cy = (self.height() / 2.0) - 10.0
        radius = 80.0
        stroke_w = 8.0

        arc_rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)

        # 1. Background Track (270 degrees sweep, starting at 225 deg)
        track_pen = QPen(QColor("#1E1E24"), stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(arc_rect, int(225 * 16), int(-270 * 16))

        # 2. Dynamic Progress Arc
        if self.value > 0:
            clamped = max(0, min(100, self.value))
            span = (clamped / 100.0) * (-270.0)

            if self.value >= 85:
                color = QColor("#EF4444")
            elif self.value >= 75:
                color = QColor("#F59E0B")
            else:
                color = QColor("#06B6D4")

            prog_pen = QPen(color, stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(prog_pen)
            painter.drawArc(arc_rect, int(225 * 16), int(span * 16))

        # 3. Center Numeric Readout & Attached Unit
        is_powered_off = (self.value == -1)
        val_str = "OFF" if is_powered_off else (f"{self.value}" if self.value > 0 else "--")
        
        val_font = QFont("Segoe UI", 42 if is_powered_off else 46, QFont.Weight.Bold)
        val_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        
        unit_font = QFont("Segoe UI", 16, QFont.Weight.DemiBold)
        unit_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)

        painter.setFont(val_font)
        fm_val = painter.fontMetrics()
        val_w = fm_val.horizontalAdvance(val_str)
        val_h = fm_val.capHeight()

        painter.setFont(unit_font)
        fm_unit = painter.fontMetrics()
        unit_w = fm_unit.horizontalAdvance(self.unit) if not is_powered_off else 0

        # Center the combined block (number + space + unit)
        gap = 4.0 if not is_powered_off and self.unit else 0.0
        total_group_w = val_w + gap + unit_w
        num_x = cx - (total_group_w / 2.0)
        num_y = cy + (val_h / 2.0) - 2

        painter.setFont(val_font)
        if is_powered_off:
            painter.setPen(QColor("#71717A"))
        else:
            painter.setPen(QColor("#FAFAFA") if self.value > 0 else QColor("#52525B"))
        painter.drawText(int(num_x), int(num_y), val_str)

        if not is_powered_off and self.unit:
            unit_color = QColor("#EF4444") if self.value >= 85 else (QColor("#F59E0B") if self.value >= 75 else QColor("#06B6D4"))
            if self.value == 0:
                unit_color = QColor("#52525B")
            painter.setFont(unit_font)
            painter.setPen(unit_color)
            painter.drawText(int(num_x + val_w + gap), int(num_y - (val_h * 0.42)), self.unit)

        # 4. Metric Subtitle (Clean Centered with Context Highlights)
        lbl_font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        lbl_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        painter.setFont(lbl_font)
        
        if is_powered_off or "OFF" in self.metric_label:
            painter.setPen(QColor("#71717A")) # Dimmed gray for OFF
        elif "GAME" in self.metric_label:
            painter.setPen(QColor("#C084FC")) # Gaming soft purple
        elif "CLOCK" in self.metric_label:
            painter.setPen(QColor("#22D3EE")) # Clock cyan
        elif "CYCLE" in self.metric_label:
            painter.setPen(QColor("#60A5FA")) # Cycle blue
        else:
            painter.setPen(QColor("#A1A1AA")) # Clean zinc-400

        sub_rect = QRectF(cx - 95, cy + 23, 190, 16)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, self.metric_label)

        # 5. Anti-Blink Status Pill
        if self.antiblink_active and not is_powered_off:
            tag_rect = QRectF(cx - 38, cy + 42, 76, 16)
            painter.setPen(QPen(QColor("#059669"), 1.0))
            painter.setBrush(QBrush(QColor("#06281E")))
            painter.drawRoundedRect(tag_rect, 4, 4)

            painter.setPen(QColor("#10B981"))
            tag_font = QFont("Segoe UI", 7, QFont.Weight.Bold)
            painter.setFont(tag_font)
            painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, "CAP 84°C")


class CycleSettingsDialog(QDialog):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Auto Cycle Playlist & Duration")
        self.setFixedSize(380, 420)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F0F12;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel {
                color: #FAFAFA;
                font-size: 11px;
            }
            .section-card {
                background-color: #141418;
                border: 1px solid #27272A;
                border-radius: 8px;
            }
            QCheckBox {
                color: #D4D4D8;
                font-size: 11px;
                font-weight: 500;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #3F3F46;
                background-color: #18181B;
            }
            QCheckBox::indicator:checked {
                background-color: #2563EB;
                border: 1px solid #3B82F6;
            }
            QPushButton.dur-btn {
                background-color: #18181B;
                border: 1px solid #27272A;
                color: #A1A1AA;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 6px;
                min-height: 22px;
            }
            QPushButton.dur-btn:hover {
                background-color: #27272A;
                color: #FAFAFA;
            }
            QPushButton.save-btn {
                background-color: #2563EB;
                border: 1px solid #3B82F6;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 600;
                padding: 6px 16px;
                border-radius: 6px;
                min-height: 24px;
            }
            QPushButton.save-btn:hover {
                background-color: #1D4ED8;
            }
            QPushButton.cancel-btn {
                background-color: #18181B;
                border: 1px solid #27272A;
                color: #A1A1AA;
                font-size: 11px;
                font-weight: 500;
                padding: 6px 16px;
                border-radius: 6px;
                min-height: 24px;
            }
            QPushButton.cancel-btn:hover {
                background-color: #27272A;
                color: #FAFAFA;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header
        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(2)
        title_lbl = QLabel("Auto Cycle Playlist & Duration")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #FAFAFA;")
        desc_lbl = QLabel("Customize hardware metrics shown on the physical pump digits.")
        desc_lbl.setStyleSheet("font-size: 10px; color: #71717A;")
        header_vbox.addWidget(title_lbl)
        header_vbox.addWidget(desc_lbl)
        layout.addLayout(header_vbox)

        # 1. Metrics Selection Card
        metrics_card = QFrame()
        metrics_card.setProperty("class", "section-card")
        m_layout = QVBoxLayout(metrics_card)
        m_layout.setContentsMargins(12, 10, 12, 10)
        m_layout.setSpacing(8)

        m_title = QLabel("INCLUDED METRICS")
        m_title.setStyleSheet("font-size: 9px; font-weight: 800; letter-spacing: 0.8px; color: #3B82F6;")
        m_layout.addWidget(m_title)

        cur_playlist = self.config.get("cycle_playlist", ["cpu_temp", "gpu_temp", "cpu_power", "cpu_load"])

        self.metric_checkboxes = {}
        available_metrics = [
            ("cpu_temp", "CPU Temperature (°C/°F)"),
            ("gpu_temp", "GPU Temperature (°C/°F)"),
            ("cpu_power", "CPU Package Power (Watts)"),
            ("cpu_load", "CPU Usage (%)"),
            ("gpu_load", "GPU Usage (%)"),
            ("ram_load", "Memory RAM Usage (%)")
        ]

        for m_key, m_label in available_metrics:
            chk = QCheckBox(m_label)
            chk.setChecked(m_key in cur_playlist)
            self.metric_checkboxes[m_key] = chk
            m_layout.addWidget(chk)

        layout.addWidget(metrics_card)

        # 2. Dwell Interval Selector Card
        interval_card = QFrame()
        interval_card.setProperty("class", "section-card")
        i_layout = QVBoxLayout(interval_card)
        i_layout.setContentsMargins(12, 10, 12, 10)
        i_layout.setSpacing(8)

        i_title = QLabel("DWELL DURATION PER METRIC")
        i_title.setStyleSheet("font-size: 9px; font-weight: 800; letter-spacing: 0.8px; color: #06B6D4;")
        i_layout.addWidget(i_title)

        dur_layout = QHBoxLayout()
        dur_layout.setSpacing(6)

        self.selected_interval = self.config.get("cycle_interval_sec", 5)
        self.dur_buttons = {}

        for sec, label in [(3, "3s"), (5, "5s (Default)"), (8, "8s"), (10, "10s")]:
            btn = QPushButton(label)
            btn.setProperty("class", "dur-btn")
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda checked, s=sec: self._select_interval(s))
            dur_layout.addWidget(btn)
            self.dur_buttons[sec] = btn

        self._update_dur_styles()
        i_layout.addLayout(dur_layout)
        layout.addWidget(interval_card)

        # 3. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("class", "cancel-btn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save Playlist")
        save_btn.setProperty("class", "save-btn")
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _select_interval(self, sec: int):
        self.selected_interval = sec
        self._update_dur_styles()

    def _update_dur_styles(self):
        active_css = "background-color: #2563EB; border: 1px solid #3B82F6; color: #FFFFFF; font-weight: 600;"
        inactive_css = "background-color: #18181B; border: 1px solid #27272A; color: #A1A1AA; font-weight: 500;"
        for sec, btn in self.dur_buttons.items():
            btn.setStyleSheet(active_css if sec == self.selected_interval else inactive_css)

    def _save_settings(self):
        new_playlist = [k for k, chk in self.metric_checkboxes.items() if chk.isChecked()]
        if not new_playlist:
            new_playlist = ["cpu_temp"]
        self.config.set("cycle_playlist", new_playlist)
        self.config.set("cycle_interval_sec", self.selected_interval)
        self.config.save()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager, service: CoolerService):
        super().__init__()
        self.config = config
        self.service = service
        self.is_closing = False
        self.is_admin = is_admin_user()
        self.last_hw_data = None

        self.setWindowTitle("Ant Esports ICEStorm-240 Dashboard")
        self.setFixedSize(540, 690)
        self.setStyleSheet(ZINC_STYLESHEET)

        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._init_ui()
        self._init_tray()

        self.service.telemetry_updated.connect(self._on_telemetry_updated)

    def _init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # 1. HEADER: Brand Typography & Micro-Pills
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        title_lbl = QLabel("ANT ESPORTS")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 800; letter-spacing: 1.5px; color: #FAFAFA;")
        
        sub_lbl = QLabel("ICESTORM 240 DASHBOARD")
        sub_lbl.setStyleSheet("font-size: 10px; font-weight: 600; letter-spacing: 0.8px; color: #06B6D4;")

        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(sub_lbl)
        header_layout.addLayout(title_vbox)

        header_layout.addStretch()

        # Admin Elevation Pill / Button (Fixed 24px height, vertically centered)
        self.admin_badge = QLabel("⚡ Ring-0 Active")
        self.admin_badge.setFixedHeight(24)
        self.admin_badge.setStyleSheet(
            "background-color: #0B192C; border: 1px solid #1D4ED8; color: #60A5FA; "
            "font-size: 10px; font-weight: 600; padding: 2px 10px; border-radius: 6px;"
        )
        header_layout.addWidget(self.admin_badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.admin_btn = QPushButton("⚡ Run as Admin")
        self.admin_btn.setFixedHeight(24)
        self.admin_btn.setStyleSheet(
            "background-color: #18181B; border: 1px solid #3B82F6; color: #3B82F6; "
            "font-size: 10px; font-weight: 600; padding: 2px 10px; border-radius: 6px;"
        )
        self.admin_btn.setToolTip("Restart with Administrator privileges to access direct AMD Zen 4 Ring-0 SMN registers.")
        self.admin_btn.clicked.connect(self._on_elevate_clicked)
        header_layout.addWidget(self.admin_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        if self.is_admin:
            self.admin_btn.hide()
        else:
            self.admin_badge.hide()

        # Cooler Connection Status Pill (Fixed 24px height, vertically centered)
        self.conn_pill = QLabel("● Connecting...")
        self.conn_pill.setFixedHeight(24)
        self.conn_pill.setStyleSheet(
            "background-color: #18181B; border: 1px solid #27272A; color: #A1A1AA; "
            "font-size: 10px; font-weight: 600; padding: 2px 10px; border-radius: 6px;"
        )
        header_layout.addWidget(self.conn_pill, alignment=Qt.AlignmentFlag.AlignVCenter)

        main_layout.addLayout(header_layout)

        # 2. HERO CARD: Continuous Vector Arc Gauge + Unified Segmented Pill
        hero_card = QFrame()
        hero_card.setProperty("class", "hero-card")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(14, 12, 14, 14)
        hero_layout.setSpacing(6)
        hero_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pump_gauge = SaaSMetricGauge()
        hero_layout.addWidget(self.pump_gauge, alignment=Qt.AlignmentFlag.AlignCenter)

        # Unified Segmented Control
        seg_container = QFrame()
        seg_container.setProperty("class", "pill-container")
        seg_layout = QHBoxLayout(seg_container)
        seg_layout.setContentsMargins(3, 3, 3, 3)
        seg_layout.setSpacing(3)

        self.btn_cpu = QPushButton("CPU Temp")
        self.btn_gpu = QPushButton("GPU Temp")
        self.btn_load = QPushButton("CPU Load")
        self.btn_power = QPushButton("CPU Power")
        self.btn_alt = QPushButton("Auto Cycle")
        self.btn_cycle_cfg = QPushButton("⚙")
        self.btn_cycle_cfg.setToolTip("Customize Auto Cycle metrics playlist and dwell duration")

        for b in [self.btn_cpu, self.btn_gpu, self.btn_load, self.btn_power, self.btn_alt]:
            b.setFixedHeight(26)
        self.btn_cycle_cfg.setFixedSize(26, 26)

        cur_metric = self.config.get("display_metric", DisplayMetric.CPU_TEMP)
        self._update_metric_button_styles(cur_metric)

        self.btn_cpu.clicked.connect(lambda: self._set_metric(DisplayMetric.CPU_TEMP))
        self.btn_gpu.clicked.connect(lambda: self._set_metric(DisplayMetric.GPU_TEMP))
        self.btn_load.clicked.connect(lambda: self._set_metric(DisplayMetric.CPU_LOAD))
        self.btn_power.clicked.connect(lambda: self._set_metric(DisplayMetric.CPU_POWER))
        self.btn_alt.clicked.connect(lambda: self._set_metric(DisplayMetric.ALTERNATING))
        self.btn_cycle_cfg.clicked.connect(self._open_cycle_settings)

        seg_layout.addWidget(self.btn_cpu)
        seg_layout.addWidget(self.btn_gpu)
        seg_layout.addWidget(self.btn_load)
        seg_layout.addWidget(self.btn_power)
        seg_layout.addWidget(self.btn_alt)
        seg_layout.addWidget(self.btn_cycle_cfg)

        hero_layout.addWidget(seg_container, alignment=Qt.AlignmentFlag.AlignCenter)

        # Smart Context Toggle Options (100% Optional, defaults to Off)
        smart_toggle_layout = QHBoxLayout()
        smart_toggle_layout.setContentsMargins(6, 4, 6, 0)
        smart_toggle_layout.setSpacing(16)
        smart_toggle_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.chk_auto_game = QCheckBox("🎮 Auto-Game Mode")
        self.chk_auto_game.setToolTip("When checked, temporarily switches pump digits to GPU Temp while running 3D games. Uncheck to strictly lock to your selected metric.")
        self.chk_auto_game.setChecked(self.config.get("auto_game_mode", False))
        self.chk_auto_game.toggled.connect(self._on_auto_game_toggled)

        self.chk_desk_clock = QCheckBox("🕒 Desk Clock (Idle)")
        self.chk_desk_clock.setToolTip("When checked, shows digital time when PC is idle for >5 minutes. Uncheck to strictly keep hardware telemetry.")
        self.chk_desk_clock.setChecked(self.config.get("desk_clock_enabled", False))
        self.chk_desk_clock.toggled.connect(self._on_desk_clock_toggled)

        smart_toggle_layout.addWidget(self.chk_auto_game)
        smart_toggle_layout.addWidget(self.chk_desk_clock)
        hero_layout.addLayout(smart_toggle_layout)

        main_layout.addWidget(hero_card)

        # 3. DISPLAY TUNING & PROTECTION STRIP (Anti-Blink & Refresh Rate)
        tuning_card = QFrame()
        tuning_card.setProperty("class", "zinc-card")
        tuning_vbox = QVBoxLayout(tuning_card)
        tuning_vbox.setContentsMargins(14, 8, 14, 8)
        tuning_vbox.setSpacing(6)

        # Row 1: Anti-Blink Protection
        ab_layout = QHBoxLayout()
        ab_layout.setContentsMargins(0, 0, 0, 0)
        ab_layout.setSpacing(12)

        ab_text_vbox = QVBoxLayout()
        ab_text_vbox.setSpacing(2)
        ab_title = QLabel("Anti-Blink Protection")
        ab_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #FAFAFA;")
        
        ab_desc = QLabel("Prevents LCD flashing during boost spikes")
        ab_desc.setStyleSheet("font-size: 10px; color: #71717A;")

        ab_text_vbox.addWidget(ab_title)
        ab_text_vbox.addWidget(ab_desc)
        ab_layout.addLayout(ab_text_vbox)

        ab_layout.addStretch()

        ab_pill_box = QFrame()
        ab_pill_box.setStyleSheet("background-color: #18181B; border: 1px solid #27272A; border-radius: 6px; padding: 2px;")
        ab_pill_layout = QHBoxLayout(ab_pill_box)
        ab_pill_layout.setContentsMargins(2, 2, 2, 2)
        ab_pill_layout.setSpacing(2)

        self.btn_cap84 = QPushButton("Cap 84°C (Safe)")
        self.btn_cap84.setFixedHeight(22)
        self.btn_cap84.setToolTip("Never transmits >= 85°C to the cooler MCU, completely eliminating rapid alarm flashing.")

        self.btn_compress = QPushButton("Compress")
        self.btn_compress.setFixedHeight(22)
        self.btn_compress.setToolTip("Smoothly compresses 75°C-100°C into the safe 75°C-84°C range.")

        self.btn_raw = QPushButton("Direct")
        self.btn_raw.setFixedHeight(22)
        self.btn_raw.setToolTip("Transmits raw temperature directly. Cooler hardware blinks when >= 85°C.")

        cur_mode = self.config.get("anti_blink_mode", AntiBlinkMode.CAP_84)
        if not self.config.get("anti_blink_enabled", True):
            cur_mode = AntiBlinkMode.RAW

        self._update_antiblink_buttons(cur_mode)

        self.btn_cap84.clicked.connect(lambda: self._set_antiblink(AntiBlinkMode.CAP_84))
        self.btn_compress.clicked.connect(lambda: self._set_antiblink(AntiBlinkMode.COMPRESS))
        self.btn_raw.clicked.connect(lambda: self._set_antiblink(AntiBlinkMode.RAW))

        ab_pill_layout.addWidget(self.btn_cap84)
        ab_pill_layout.addWidget(self.btn_compress)
        ab_pill_layout.addWidget(self.btn_raw)
        ab_layout.addWidget(ab_pill_box)
        tuning_vbox.addLayout(ab_layout)

        # Subtle divider
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #1F1F23;")
        tuning_vbox.addWidget(sep)

        # Row 2: Display Refresh Rate (Polling Speed)
        poll_layout = QHBoxLayout()
        poll_layout.setContentsMargins(0, 0, 0, 0)
        poll_layout.setSpacing(12)

        poll_text_vbox = QVBoxLayout()
        poll_text_vbox.setSpacing(2)
        poll_title = QLabel("Display Refresh Rate")
        poll_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #FAFAFA;")
        
        poll_desc = QLabel("Controls physical digit update cadence")
        poll_desc.setStyleSheet("font-size: 10px; color: #71717A;")

        poll_text_vbox.addWidget(poll_title)
        poll_text_vbox.addWidget(poll_desc)
        poll_layout.addLayout(poll_text_vbox)

        poll_layout.addStretch()

        poll_pill_box = QFrame()
        poll_pill_box.setStyleSheet("background-color: #18181B; border: 1px solid #27272A; border-radius: 6px; padding: 2px;")
        poll_pill_layout = QHBoxLayout(poll_pill_box)
        poll_pill_layout.setContentsMargins(2, 2, 2, 2)
        poll_pill_layout.setSpacing(2)

        self.btn_poll_05 = QPushButton("0.5s")
        self.btn_poll_05.setFixedHeight(22)
        self.btn_poll_05.setToolTip("Fast update cadence (twice per second).")

        self.btn_poll_10 = QPushButton("1.0s (Normal)")
        self.btn_poll_10.setFixedHeight(22)
        self.btn_poll_10.setToolTip("Calm standard cadence (once per second). Recommended.")

        self.btn_poll_20 = QPushButton("2.0s (Relaxed)")
        self.btn_poll_20.setFixedHeight(22)
        self.btn_poll_20.setToolTip("Relaxed slow cadence (once every 2 seconds).")

        cur_poll = self.config.get("update_interval_ms", 1000)
        self._update_poll_buttons(cur_poll)

        self.btn_poll_05.clicked.connect(lambda: self._set_polling_rate(500))
        self.btn_poll_10.clicked.connect(lambda: self._set_polling_rate(1000))
        self.btn_poll_20.clicked.connect(lambda: self._set_polling_rate(2000))

        poll_pill_layout.addWidget(self.btn_poll_05)
        poll_pill_layout.addWidget(self.btn_poll_10)
        poll_pill_layout.addWidget(self.btn_poll_20)
        poll_layout.addWidget(poll_pill_box)
        tuning_vbox.addLayout(poll_layout)

        # Subtle divider
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color: #1F1F23;")
        tuning_vbox.addWidget(sep2)

        # Row 3: Display Power (LED Digits ON / OFF)
        pwr_layout = QHBoxLayout()
        pwr_layout.setContentsMargins(0, 0, 0, 0)
        pwr_layout.setSpacing(12)

        pwr_text_vbox = QVBoxLayout()
        pwr_text_vbox.setSpacing(2)
        pwr_title = QLabel("Pump LED Display Power")
        pwr_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #FAFAFA;")
        
        pwr_desc = QLabel("Stop LED readout; pump turns off via hardware standby (~1 min)")
        pwr_desc.setStyleSheet("font-size: 10px; color: #71717A;")

        pwr_text_vbox.addWidget(pwr_title)
        pwr_text_vbox.addWidget(pwr_desc)
        pwr_layout.addLayout(pwr_text_vbox)

        pwr_layout.addStretch()

        pwr_pill_box = QFrame()
        pwr_pill_box.setStyleSheet("background-color: #18181B; border: 1px solid #27272A; border-radius: 6px; padding: 2px;")
        pwr_pill_layout = QHBoxLayout(pwr_pill_box)
        pwr_pill_layout.setContentsMargins(2, 2, 2, 2)
        pwr_pill_layout.setSpacing(2)

        self.btn_pwr_on = QPushButton("💡 ON")
        self.btn_pwr_on.setFixedHeight(22)
        self.btn_pwr_on.setToolTip("Enable pump digital LED display readout.")

        self.btn_pwr_off = QPushButton("🌑 OFF")
        self.btn_pwr_off.setFixedHeight(22)
        self.btn_pwr_off.setToolTip("Stops LED updates so pump display turns off via hardware standby (~1 min). Cooling remains 100% active.")

        cur_pwr = self.config.get("display_power_on", True)
        self._update_display_power_buttons(cur_pwr)

        self.btn_pwr_on.clicked.connect(lambda: self._set_display_power(True))
        self.btn_pwr_off.clicked.connect(lambda: self._set_display_power(False))

        pwr_pill_layout.addWidget(self.btn_pwr_on)
        pwr_pill_layout.addWidget(self.btn_pwr_off)
        pwr_layout.addWidget(pwr_pill_box)
        tuning_vbox.addLayout(pwr_layout)

        main_layout.addWidget(tuning_card)

        # 4. HARDWARE TELEMETRY KPI CARDS (CPU, GPU, RAM)
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)

        # CPU KPI Card
        self.cpu_card = QFrame()
        self.cpu_card.setProperty("class", "zinc-card")
        c_layout = QVBoxLayout(self.cpu_card)
        c_layout.setContentsMargins(12, 10, 12, 10)
        c_layout.setSpacing(4)

        c_top = QHBoxLayout()
        lbl_cpu_cat = QLabel("CPU")
        lbl_cpu_cat.setStyleSheet("font-size: 11px; font-weight: 700; color: #3B82F6;")
        self.lbl_cpu_name = QLabel("Ryzen 9 7900X")
        self.lbl_cpu_name.setStyleSheet("font-size: 10px; color: #A1A1AA; font-weight: 500;")
        c_top.addWidget(lbl_cpu_cat)
        c_top.addStretch()
        c_top.addWidget(self.lbl_cpu_name)
        c_layout.addLayout(c_top)

        self.lbl_cpu_val = QLabel("--.- °C")
        self.lbl_cpu_val.setStyleSheet("font-size: 20px; font-weight: 700; color: #FAFAFA; margin-top: 1px;")
        c_layout.addWidget(self.lbl_cpu_val)

        self.cpu_bar = MicroProgressBar()
        c_layout.addWidget(self.cpu_bar)

        self.lbl_cpu_sub = QLabel("Load: --%  •  -- MHz")
        self.lbl_cpu_sub.setStyleSheet("font-size: 10px; color: #71717A; margin-top: 2px;")
        c_layout.addWidget(self.lbl_cpu_sub)
        stats_layout.addWidget(self.cpu_card)

        # GPU KPI Card
        self.gpu_card = QFrame()
        self.gpu_card.setProperty("class", "zinc-card")
        g_layout = QVBoxLayout(self.gpu_card)
        g_layout.setContentsMargins(12, 10, 12, 10)
        g_layout.setSpacing(4)

        g_top = QHBoxLayout()
        lbl_gpu_cat = QLabel("GPU")
        lbl_gpu_cat.setStyleSheet("font-size: 11px; font-weight: 700; color: #10B981;")
        self.lbl_gpu_name = QLabel("Radeon Graphics")
        self.lbl_gpu_name.setStyleSheet("font-size: 10px; color: #A1A1AA; font-weight: 500;")
        g_top.addWidget(lbl_gpu_cat)
        g_top.addStretch()
        g_top.addWidget(self.lbl_gpu_name)
        g_layout.addLayout(g_top)

        self.lbl_gpu_val = QLabel("--.- °C")
        self.lbl_gpu_val.setStyleSheet("font-size: 20px; font-weight: 700; color: #FAFAFA; margin-top: 1px;")
        g_layout.addWidget(self.lbl_gpu_val)

        self.gpu_bar = MicroProgressBar()
        g_layout.addWidget(self.gpu_bar)

        self.lbl_gpu_sub = QLabel("Load: --%  •  -- MHz")
        self.lbl_gpu_sub.setStyleSheet("font-size: 10px; color: #71717A; margin-top: 2px;")
        g_layout.addWidget(self.lbl_gpu_sub)
        stats_layout.addWidget(self.gpu_card)

        # RAM KPI Card
        self.ram_card = QFrame()
        self.ram_card.setProperty("class", "zinc-card")
        r_layout = QVBoxLayout(self.ram_card)
        r_layout.setContentsMargins(12, 10, 12, 10)
        r_layout.setSpacing(4)

        r_top = QHBoxLayout()
        lbl_ram_cat = QLabel("MEMORY")
        lbl_ram_cat.setStyleSheet("font-size: 11px; font-weight: 700; color: #A855F7;")
        self.lbl_ram_name = QLabel("DDR5 6000")
        self.lbl_ram_name.setStyleSheet("font-size: 10px; color: #A1A1AA; font-weight: 500;")
        r_top.addWidget(lbl_ram_cat)
        r_top.addStretch()
        r_top.addWidget(self.lbl_ram_name)
        r_layout.addLayout(r_top)

        self.lbl_ram_val = QLabel("--%")
        self.lbl_ram_val.setStyleSheet("font-size: 20px; font-weight: 700; color: #FAFAFA; margin-top: 1px;")
        r_layout.addWidget(self.lbl_ram_val)

        self.ram_bar = MicroProgressBar()
        r_layout.addWidget(self.ram_bar)

        self.lbl_ram_sub = QLabel("Used: -- / -- GB")
        self.lbl_ram_sub.setStyleSheet("font-size: 10px; color: #71717A; margin-top: 2px;")
        r_layout.addWidget(self.lbl_ram_sub)
        stats_layout.addWidget(self.ram_card)

        main_layout.addLayout(stats_layout)

        # 5. FOOTER: Status Line, Autostart Checkbox, Minimize Action
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(12)

        self.lbl_source = QLabel("Sensor Engine: Initializing...")
        self.lbl_source.setStyleSheet("font-size: 11px; color: #71717A;")
        footer_layout.addWidget(self.lbl_source)

        footer_layout.addStretch()

        self.chk_autostart = QCheckBox("Start with Windows")
        self.chk_autostart.setChecked(self.config.get("autostart", False))
        self.chk_autostart.toggled.connect(self._on_autostart_toggled)
        footer_layout.addWidget(self.chk_autostart)

        self.btn_hide = QPushButton("Hide to Tray")
        self.btn_hide.setProperty("class", "footer-btn")
        self.btn_hide.clicked.connect(self.hide)
        footer_layout.addWidget(self.btn_hide)

        main_layout.addLayout(footer_layout)

        self.setCentralWidget(main_widget)

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.windowIcon())
        self.tray_menu = QMenu()

        title_action = QAction("Ant Esports ICEStorm-240", self)
        title_action.setEnabled(False)
        self.tray_menu.addAction(title_action)
        self.tray_menu.addSeparator()

        show_action = QAction("Open Dashboard", self)
        bold_font = QFont()
        bold_font.setBold(True)
        show_action.setFont(bold_font)
        show_action.triggered.connect(self._show_window)
        self.tray_menu.addAction(show_action)

        self.tray_menu.addSeparator()

        # Display Metric Submenu
        metric_menu = self.tray_menu.addMenu("Display Metric")
        self.tray_metric_actions = {}
        for m_code, m_label in [
            (DisplayMetric.CPU_TEMP, "CPU Temperature"),
            (DisplayMetric.GPU_TEMP, "GPU Temperature"),
            (DisplayMetric.CPU_LOAD, "CPU Load"),
            (DisplayMetric.CPU_POWER, "CPU Package Power (W)"),
            (DisplayMetric.ALTERNATING, "Auto Cycle")
        ]:
            act = QAction(m_label, self)
            act.setCheckable(True)
            act.setChecked(self.config.get("display_metric", DisplayMetric.CPU_TEMP) == m_code)
            act.triggered.connect(lambda checked, m=m_code: self._set_metric(m))
            metric_menu.addAction(act)
            self.tray_metric_actions[m_code] = act

        metric_menu.addSeparator()
        act_cycle_cfg = QAction("⚙ Customize Auto Cycle Playlist...", self)
        act_cycle_cfg.triggered.connect(self._open_cycle_settings)
        metric_menu.addAction(act_cycle_cfg)

        # Anti-Blink Submenu
        antiblink_menu = self.tray_menu.addMenu("Anti-Blink Mode")
        self.tray_ab_actions = {}
        for ab_code, ab_label in [
            (AntiBlinkMode.CAP_84, "Cap at 84°C (Safe)"),
            (AntiBlinkMode.COMPRESS, "Compress Range (70-99°C)"),
            (AntiBlinkMode.RAW, "Direct Uncapped (Raw)")
        ]:
            act = QAction(ab_label, self)
            act.setCheckable(True)
            cur_mode = self.config.get("anti_blink_mode", AntiBlinkMode.CAP_84) if self.config.get("anti_blink_enabled", True) else AntiBlinkMode.RAW
            act.setChecked(cur_mode == ab_code)
            act.triggered.connect(lambda checked, a=ab_code: self._set_antiblink(a))
            antiblink_menu.addAction(act)
            self.tray_ab_actions[ab_code] = act

        # Refresh Rate Submenu
        poll_menu = self.tray_menu.addMenu("Refresh Rate")
        self.tray_poll_actions = {}
        for p_ms, p_label in [
            (500, "0.5s (Fast)"),
            (1000, "1.0s (Normal - Recommended)"),
            (2000, "2.0s (Relaxed)")
        ]:
            act = QAction(p_label, self)
            act.setCheckable(True)
            act.setChecked(self.config.get("update_interval_ms", 1000) == p_ms)
            act.triggered.connect(lambda checked, ms=p_ms: self._set_polling_rate(ms))
            poll_menu.addAction(act)
            self.tray_poll_actions[p_ms] = act

        self.act_display_power = QAction("💡 Pump LED Display (Power ON)", self)
        self.act_display_power.setCheckable(True)
        self.act_display_power.setChecked(self.config.get("display_power_on", True))
        self.act_display_power.triggered.connect(self._set_display_power)
        self.tray_menu.addAction(self.act_display_power)

        # Phase 2: Smart Context & Display Features Submenu
        smart_menu = self.tray_menu.addMenu("Smart Display Features")
        
        self.act_game_mode = QAction("🎮 Auto-Game Thermals (Switch to GPU in 3D Games)", self)
        self.act_game_mode.setCheckable(True)
        self.act_game_mode.setChecked(self.config.get("auto_game_mode", False))
        self.act_game_mode.triggered.connect(self._on_auto_game_toggled)
        smart_menu.addAction(self.act_game_mode)

        self.act_desk_clock = QAction("🕒 Desk Clock Idle Mode (Show Time when Idle)", self)
        self.act_desk_clock.setCheckable(True)
        self.act_desk_clock.setChecked(self.config.get("desk_clock_enabled", False))
        self.act_desk_clock.triggered.connect(self._on_desk_clock_toggled)
        smart_menu.addAction(self.act_desk_clock)

        smart_menu.addSeparator()

        self.act_smooth = QAction("✨ Predictive Smooth Stepping", self)
        self.act_smooth.setCheckable(True)
        self.act_smooth.setChecked(self.config.get("smooth_stepping", True))
        self.act_smooth.triggered.connect(lambda checked: self._toggle_config_bool("smooth_stepping", checked))
        smart_menu.addAction(self.act_smooth)

        self.act_sweep = QAction("🚀 Startup Gauge Sweep POST Sequence", self)
        self.act_sweep.setCheckable(True)
        self.act_sweep.setChecked(self.config.get("startup_animation", True))
        self.act_sweep.triggered.connect(lambda checked: self._toggle_config_bool("startup_animation", checked))
        smart_menu.addAction(self.act_sweep)

        self.tray_menu.addSeparator()

        if not is_admin_user():
            elevate_action = QAction("Restart as Admin", self)
            elevate_action.triggered.connect(self._on_elevate_clicked)
            self.tray_menu.addAction(elevate_action)
            self.tray_menu.addSeparator()

        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self._exit_app)
        self.tray_menu.addAction(quit_action)

        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.setToolTip("Ant Esports ICEStorm-240 Dashboard")
        self.tray.show()

    def _show_window(self):
        self.showNormal()
        self.activateWindow()

    def _exit_app(self):
        self.is_closing = True
        self.service.stop()
        QApplication.instance().quit()

    def closeEvent(self, event):
        app = QApplication.instance()
        if app and getattr(app, "isSavingSession", lambda: False)():
            self.service.stop()
            event.accept()
            return

        if not self.is_closing and self.config.get("minimize_to_tray_on_close", True):
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Ant Esports ICEStorm-240",
                "Dashboard minimized to system tray. Telemetry monitor active.",
                QSystemTrayIcon.MessageIcon.Information,
                1500
            )
        else:
            self.service.stop()
            event.accept()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._show_window()

    def _on_elevate_clicked(self):
        restart_as_admin()

    def _set_metric(self, metric: str):
        self.config.set("display_metric", metric)
        self.config.save()
        self._update_metric_button_styles(metric)
        for m_code, act in getattr(self, "tray_metric_actions", {}).items():
            act.setChecked(m_code == metric)

    def _update_metric_button_styles(self, active_metric: str):
        active_css = (
            "background-color: #2563EB; color: #FFFFFF; font-weight: 600; "
            "border: none; border-radius: 6px; padding: 4px 14px; font-size: 11px;"
        )
        inactive_css = (
            "background-color: transparent; color: #A1A1AA; font-weight: 500; "
            "border: none; border-radius: 6px; padding: 4px 14px; font-size: 11px;"
        )

        self.btn_cpu.setStyleSheet(active_css if active_metric == DisplayMetric.CPU_TEMP else inactive_css)
        self.btn_gpu.setStyleSheet(active_css if active_metric == DisplayMetric.GPU_TEMP else inactive_css)
        self.btn_load.setStyleSheet(active_css if active_metric == DisplayMetric.CPU_LOAD else inactive_css)
        self.btn_power.setStyleSheet(active_css if active_metric == DisplayMetric.CPU_POWER else inactive_css)
        self.btn_alt.setStyleSheet(active_css if active_metric == DisplayMetric.ALTERNATING else inactive_css)
        if hasattr(self, "btn_cycle_cfg"):
            cfg_css = (
                "background-color: #1E3A8A; color: #93C5FD; font-size: 12px; font-weight: bold; "
                "border: 1px solid #3B82F6; border-radius: 6px;"
            ) if active_metric == DisplayMetric.ALTERNATING else (
                "background-color: transparent; color: #71717A; font-size: 12px; "
                "border: none; border-radius: 6px;"
            )
            self.btn_cycle_cfg.setStyleSheet(cfg_css)

    def _open_cycle_settings(self):
        dlg = CycleSettingsDialog(self.config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if self.config.get("display_metric") == DisplayMetric.ALTERNATING:
                # Reset cycle state immediately so user sees their new selection without delay
                if hasattr(self.service, "_playlist_idx"):
                    self.service._playlist_idx = 0
                if hasattr(self.service, "_last_alt_switch_time"):
                    self.service._last_alt_switch_time = 0.0

    def _set_antiblink(self, mode: str):
        if mode == AntiBlinkMode.RAW:
            self.config.set("anti_blink_enabled", False)
            self.config.set("anti_blink_mode", AntiBlinkMode.RAW)
        else:
            self.config.set("anti_blink_enabled", True)
            self.config.set("anti_blink_mode", mode)
        self.config.save()
        self._update_antiblink_buttons(mode)
        for ab_code, act in getattr(self, "tray_ab_actions", {}).items():
            act.setChecked(ab_code == mode)

    def _update_antiblink_buttons(self, active_mode: str):
        inactive_css = (
            "background-color: transparent; color: #71717A; font-weight: 500; "
            "border: none; border-radius: 4px; padding: 2px 8px; font-size: 10px;"
        )
        self.btn_cap84.setStyleSheet(inactive_css)
        self.btn_compress.setStyleSheet(inactive_css)
        self.btn_raw.setStyleSheet(inactive_css)

        if active_mode == AntiBlinkMode.CAP_84:
            self.btn_cap84.setStyleSheet(
                "background-color: #064E3B; color: #34D399; font-weight: 600; "
                "border: none; border-radius: 4px; padding: 2px 8px; font-size: 10px;"
            )
        elif active_mode == AntiBlinkMode.COMPRESS:
            self.btn_compress.setStyleSheet(
                "background-color: #1E3A8A; color: #60A5FA; font-weight: 600; "
                "border: none; border-radius: 4px; padding: 2px 8px; font-size: 10px;"
            )
        elif active_mode == AntiBlinkMode.RAW:
            self.btn_raw.setStyleSheet(
                "background-color: #7F1D1D; color: #F87171; font-weight: 600; "
                "border: none; border-radius: 4px; padding: 2px 8px; font-size: 10px;"
            )

    def _set_polling_rate(self, interval_ms: int):
        self.config.set("update_interval_ms", interval_ms)
        self.config.save()
        self._update_poll_buttons(interval_ms)
        for p_val, act in getattr(self, "tray_poll_actions", {}).items():
            act.setChecked(p_val == interval_ms)

    def _update_poll_buttons(self, active_ms: int):
        inactive_css = (
            "background-color: transparent; color: #71717A; font-weight: 500; "
            "border: none; border-radius: 4px; padding: 2px 8px; font-size: 10px;"
        )
        active_css = (
            "background-color: #1E3A8A; color: #60A5FA; font-weight: 600; "
            "border: none; border-radius: 4px; padding: 2px 8px; font-size: 10px;"
        )
        self.btn_poll_05.setStyleSheet(active_css if active_ms == 500 else inactive_css)
        self.btn_poll_10.setStyleSheet(active_css if active_ms == 1000 else inactive_css)
        self.btn_poll_20.setStyleSheet(active_css if active_ms == 2000 else inactive_css)

    def _set_display_power(self, power_on: bool):
        self.config.set("display_power_on", power_on)
        self.config.save()
        self._update_display_power_buttons(power_on)
        if hasattr(self, "act_display_power"):
            self.act_display_power.blockSignals(True)
            self.act_display_power.setChecked(power_on)
            self.act_display_power.setText("💡 Pump LED Display (Power ON)" if power_on else "🌑 Pump LED Display (Power OFF)")
            self.act_display_power.blockSignals(False)

    def _update_display_power_buttons(self, is_on: bool):
        inactive_css = (
            "background-color: transparent; color: #71717A; font-weight: 500; "
            "border: none; border-radius: 4px; padding: 2px 10px; font-size: 10px;"
        )
        on_active_css = (
            "background-color: #052E16; color: #4ADE80; font-weight: 600; "
            "border: 1px solid #15803D; border-radius: 4px; padding: 2px 10px; font-size: 10px;"
        )
        off_active_css = (
            "background-color: #3F3F46; color: #FAFAFA; font-weight: 600; "
            "border: 1px solid #71717A; border-radius: 4px; padding: 2px 10px; font-size: 10px;"
        )
        if hasattr(self, "btn_pwr_on"):
            self.btn_pwr_on.setStyleSheet(on_active_css if is_on else inactive_css)
        if hasattr(self, "btn_pwr_off"):
            self.btn_pwr_off.setStyleSheet(off_active_css if not is_on else inactive_css)

    def _toggle_config_bool(self, key: str, value: bool):
        self.config.set(key, value)
        self.config.save()

    def _on_auto_game_toggled(self, checked: bool):
        self.config.set("auto_game_mode", checked)
        self.config.save()
        if hasattr(self, "chk_auto_game") and self.chk_auto_game.isChecked() != checked:
            self.chk_auto_game.blockSignals(True)
            self.chk_auto_game.setChecked(checked)
            self.chk_auto_game.blockSignals(False)
        if hasattr(self, "act_game_mode") and self.act_game_mode.isChecked() != checked:
            self.act_game_mode.blockSignals(True)
            self.act_game_mode.setChecked(checked)
            self.act_game_mode.blockSignals(False)

    def _on_desk_clock_toggled(self, checked: bool):
        self.config.set("desk_clock_enabled", checked)
        self.config.save()
        if hasattr(self, "chk_desk_clock") and self.chk_desk_clock.isChecked() != checked:
            self.chk_desk_clock.blockSignals(True)
            self.chk_desk_clock.setChecked(checked)
            self.chk_desk_clock.blockSignals(False)
        if hasattr(self, "act_desk_clock") and self.act_desk_clock.isChecked() != checked:
            self.act_desk_clock.blockSignals(True)
            self.act_desk_clock.setChecked(checked)
            self.act_desk_clock.blockSignals(False)

    def nativeEvent(self, eventType, message):
        """Listen for native Windows power broadcast messages to auto-recover USB HID on wake."""
        if eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0218:  # WM_POWERBROADCAST
                    if msg.wParam in (0x0012, 0x0007):  # PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND
                        print("[MainWindow] Windows power resume event received - triggering cooler re-enumeration")
                        self.service.reconnect_after_wake()
            except Exception:
                pass
        return (False, 0)

    def _on_autostart_toggled(self, checked: bool):
        self.config.set("autostart", checked)
        self.config.save()
        self._set_windows_autostart(checked)

    def _set_windows_autostart(self, enable: bool):
        self.config.set_autostart(enable)

    def _render_tray_icon(self, val: int, unit_sym: str, border_color: QColor) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 1. Dark pill badge background with thermal accent ring
        painter.setPen(QPen(border_color, 4.0))
        painter.setBrush(QBrush(QColor(14, 14, 18, 235)))
        painter.drawRoundedRect(3, 3, 58, 58, 14, 14)

        # 2. Numerical digits
        is_off = (val == -1)
        val_str = "OFF" if is_off else (str(val) if val >= 0 else "--")
        font = QFont("Segoe UI", 21 if is_off else 25, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#71717A") if is_off else QColor("#FAFAFA")))
        painter.drawText(QRectF(0, 5, 64, 44), Qt.AlignmentFlag.AlignCenter, val_str)

        # 3. Dynamic unit accent dot
        if not is_off:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(border_color))
            painter.drawEllipse(QPointF(32, 53), 3.5, 3.5)

        painter.end()
        return QIcon(pixmap)

    def _on_telemetry_updated(self, hw_data, displayed_val: int, unit: str, is_antiblink_active: bool, connected: bool, metric_name: str):
        self.last_hw_data = hw_data

        # Update Hero Gauge
        unit_sym = "°C" if unit in (TemperatureUnit.CELSIUS, "°C", "C", "celsius") else ("°F" if unit in (TemperatureUnit.FAHRENHEIT, "°F", "F") else ("W" if unit == "W" else ("%" if unit == "%" else "")))
        
        # Professional uppercase metric title with smart mode indicators
        clean_name = metric_name.upper()
        if "DISPLAY OFF" in clean_name:
            clean_name = "DISPLAY POWER OFF"
            unit_sym = ""
        elif "DESK CLOCK" in clean_name:
            clean_name = "🕒 DESK CLOCK"
            unit_sym = ""
        elif "GAME" in clean_name:
            clean_name = "🎮 AUTO-GAME: GPU TEMP"
        elif "CYCLE" in clean_name:
            clean_name = "🔄 " + clean_name.replace(" (CYCLE)", "")
        elif "CPU" in clean_name and "TEMP" in clean_name:
            clean_name = "CPU TEMPERATURE"
        elif "GPU" in clean_name and "TEMP" in clean_name:
            clean_name = "GPU TEMPERATURE"
        elif "POWER" in clean_name:
            clean_name = "CPU PACKAGE POWER"
        elif "LOAD" in clean_name or "USAGE" in clean_name:
            clean_name = "CPU LOAD"

        self.pump_gauge.set_data(displayed_val, unit_sym, clean_name, is_antiblink_active)

        # Update Connection Badge (Fixed 24px height)
        if connected:
            self.conn_pill.setText("● Connected")
            self.conn_pill.setStyleSheet(
                "background-color: #052E16; border: 1px solid #15803D; color: #4ADE80; "
                "font-size: 10px; font-weight: 600; padding: 2px 10px; border-radius: 6px;"
            )
        else:
            self.conn_pill.setText("○ Disconnected")
            self.conn_pill.setStyleSheet(
                "background-color: #3B0712; border: 1px solid #991B1B; color: #F87171; "
                "font-size: 10px; font-weight: 600; padding: 2px 10px; border-radius: 6px;"
            )

        # Update CPU Telemetry & Bar
        cpu_display_name = hw_data.cpu_name.replace("AMD ", "").strip()
        self.lbl_cpu_name.setText(cpu_display_name)
        if hw_data.cpu_temp > 0.0:
            self.lbl_cpu_val.setText(f"{hw_data.cpu_temp:.1f} °C")
            self.lbl_cpu_sub.setText(f"Load: {hw_data.cpu_load:.0f}%  •  {hw_data.cpu_clock} MHz")
            
            bar_color = QColor("#EF4444") if hw_data.cpu_temp >= 85 else (QColor("#F59E0B") if hw_data.cpu_temp >= 75 else QColor("#06B6D4"))
            self.cpu_bar.setValue(hw_data.cpu_temp, bar_color)
        else:
            self.lbl_cpu_val.setText("-- °C")
            if not hw_data.is_admin:
                self.lbl_cpu_sub.setText(f"Load: {hw_data.cpu_load:.0f}%  •  Admin Req")
            else:
                self.lbl_cpu_sub.setText(f"Load: {hw_data.cpu_load:.0f}%  •  Syncing")
            self.cpu_bar.setValue(0, QColor("#3B82F6"))

        # Update GPU Telemetry & Bar
        gpu_display_name = hw_data.gpu_name.replace("AMD ", "").replace("(TM)", "").strip()
        self.lbl_gpu_name.setText(gpu_display_name)
        if hw_data.gpu_temp > 0.0:
            self.lbl_gpu_val.setText(f"{hw_data.gpu_temp:.1f} °C")
            self.lbl_gpu_sub.setText(f"Load: {hw_data.gpu_load:.0f}%  •  {hw_data.gpu_clock} MHz")
            self.gpu_bar.setValue(hw_data.gpu_temp, QColor("#10B981"))
        else:
            self.lbl_gpu_val.setText("-- °C")
            self.lbl_gpu_sub.setText(f"Load: {hw_data.gpu_load:.0f}%")
            self.gpu_bar.setValue(0, QColor("#10B981"))

        # Update Memory Telemetry & Bar
        ram_used_gb = hw_data.ram_used_mb / 1024.0
        ram_total_gb = hw_data.ram_total_mb / 1024.0 if hw_data.ram_total_mb > 0 else 15.5
        self.lbl_ram_val.setText(f"{hw_data.ram_load:.0f}%")
        self.lbl_ram_sub.setText(f"Used: {ram_used_gb:.1f} / {ram_total_gb:.1f} GB")
        self.ram_bar.setValue(hw_data.ram_load, QColor("#A855F7"))

        # Update Sensor Engine Status Line
        self.lbl_source.setText(f"Sensor Engine: {hw_data.sensor_source}")

        # Update Dynamic Tray Tooltip and Live Digit Mirror Icon
        if hasattr(self, "tray") and self.tray:
            conn_text = "Connected" if connected else "Disconnected"
            tooltip_lines = [
                "Ant Esports ICEStorm-240",
                f"Status: {conn_text}",
                f"CPU: {hw_data.cpu_temp:.1f}°C ({hw_data.cpu_load:.0f}%)",
                f"GPU: {hw_data.gpu_temp:.1f}°C ({hw_data.gpu_load:.0f}%)",
                f"Pump Display: {clean_name}"
            ]
            self.tray.setToolTip("\n".join(tooltip_lines))
            
            if displayed_val == -1:
                accent_color = QColor("#52525B") # Muted zinc
            elif unit_sym == "":
                accent_color = QColor("#06B6D4") # Desk Clock cyan
            elif displayed_val >= 85 and "°" in unit_sym:
                accent_color = QColor("#EF4444") # High temp red
            elif displayed_val >= 75 and "°" in unit_sym:
                accent_color = QColor("#F59E0B") # Warm temp amber
            elif unit_sym == "W":
                accent_color = QColor("#A855F7") # CPU Watts purple
            elif unit_sym == "%":
                accent_color = QColor("#3B82F6") # Compute load blue
            else:
                accent_color = QColor("#10B981") # Cool emerald
            self.tray.setIcon(self._render_tray_icon(displayed_val, unit_sym, accent_color))
