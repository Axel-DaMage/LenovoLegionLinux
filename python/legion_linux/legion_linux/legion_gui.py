#!/usr/bin/python3
# pylint: disable=too-many-lines
# pylint: disable=c-extension-no-member
import sys
import os
import os.path
import traceback
import logging
import random
import time
from typing import List, Optional
from PyQt6 import QtGui, QtCore
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, QRunnable, QThreadPool
from PyQt6.QtGui import QAction, QGuiApplication, QPainter, QPainterPath, QPen, QColor
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QLabel, \
    QVBoxLayout, QGridLayout, QLineEdit, QPushButton, QComboBox, QGroupBox, \
    QCheckBox, QSystemTrayIcon, QMenu, QScrollArea, QMessageBox, QSpinBox, QTextBrowser, QHBoxLayout, QFileDialog, QSizePolicy, QProgressBar
# Make it possible to run without installation
# pylint: disable=# pylint: disable=wrong-import-position
sys.path.insert(0, os.path.dirname(__file__) + "/..")
import legion_linux.legion
from legion_linux.legion import LegionModelFacade, FanCurve, FanCurveEntry, FileFeature, \
    IntFileFeature, GsyncFeature, SystemNotificationSender, DiagnosticMsg


def get_color_mode():
    # Try detecting the current color mode (dark/light)
    # As darkdetect is not a system package, make it work if
    # it is not installed
    try:
        # pylint: disable=import-outside-toplevel
        import darkdetect
        if darkdetect.theme() == 'Dark':
            return 'dark'
        if darkdetect.theme() == 'Light':
            return 'light'
    except ImportError as err:
        log.error("Error using darkdetect. Is it installed?")
        log.error(str(err))
    return 'unknown'

# pylint: disable=too-few-public-methods

logging.basicConfig()
log = logging.getLogger(legion_linux.legion.__name__)
log.setLevel('INFO')




class MonitorSignals(QtCore.QObject):
    # cpu_temp, gpu_temp, fan1_rpm, fan2_rpm, profile, cpu_usage, ram_usage(tuple), gpu_usage(tuple)
    statsUpdated = QtCore.pyqtSignal(object, object, object, object, str, object, object, object)


class MonitorWorker(QRunnable):
    def __init__(self, model:LegionModelFacade):
        super().__init__()
        self.model = model
        self.running = False
        self.notification_sender = SystemNotificationSender()
        self.signals = MonitorSignals()
        self.system_stats = SystemStats()


    @pyqtSlot()
    def run(self):
        log.info("Start monitoring thread")

        # The thread itself
        while self.running:
            diag_msgs: List[DiagnosticMsg] = []
            for mon in self.model.monitors:
                try:
                    # log.info(f"Running monitor: {mon}")
                    diag_msgs = diag_msgs + mon.run()
                # pylint: disable=broad-except
                except Exception as err:
                    log.error(f"Error in monitor {mon}: {err}")
            
            # Emit stats for the Dashboard
            try:
                # log.info("Reading stats for dashboard...")
                cpu_temp = float(self.model.fancurve_io.get_cpu_temp())
                gpu_temp = float(self.model.fancurve_io.get_gpu_temp())
                # log.info("Read temps")
                fan1_rpm = int(self.model.fancurve_io.get_fan_1_rpm())
                fan2_rpm = int(self.model.fancurve_io.get_fan_2_rpm())
                # log.info("Read fans")
                # Warning: platform_profile might be the crash source if file read fails weirdly
                profile = str(self.model.platform_profile.get())
                
                # New Stats
                cpu_usage = self.system_stats.get_cpu_usage()
                ram_usage = self.system_stats.get_ram_usage()
                gpu_usage = self.system_stats.get_gpu_usage()

                self.signals.statsUpdated.emit(cpu_temp, gpu_temp, fan1_rpm, fan2_rpm, profile, cpu_usage, ram_usage, gpu_usage)
            except Exception as err:
                log.error("Error reading stats for dashboard: %s", str(err))
            
            for msg in diag_msgs:
                if msg.has_value and msg.filter_do_output:
                     self.notification_sender.notify('Legion', msg.msg)
            time.sleep(1.0) # Faster monitoring for the dashboard

        log.info("Finishing monitoring thread")


class MinimalistSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.last_y = 0
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QSpinBox {
                border: 1px solid #333;
                border-radius: 5px;
                padding: 2px;
                background-color: #1a1a1a;
                color: #eee;
            }
            QSpinBox:focus {
                border: 1px solid #00c8ff;
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_y = event.pos().y()
            self.setFocus()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            current_y = event.pos().y()
            delta = self.last_y - current_y
            # Cumulative delta to allow fine control
            if abs(delta) >= 2:
                steps = delta // 2
                self.setValue(self.value() + (steps * self.singleStep()))
                self.last_y = current_y
        super().mouseMoveEvent(event)


def mark_error(checkbox: QCheckBox):
    checkbox.setStyleSheet(
        "QCheckBox::indicator {background-color : red;} "
        "QCheckBox:disabled{background-color : red;} "
        "QCheckBox {background-color : red;}")


def mark_error_combobox(combobox: QComboBox):
    combobox.setStyleSheet(
        "QComboBox::indicator {background-color : red;} "
        "QComboBox:disabled{background-color : red;} "
        "QComboBox {background-color : red;}")


def log_error(ex: Exception):
    if isinstance(ex, OSError) and ex.errno == 22:
        print("Feature not supported or invalid argument (Errno 22).")
    else:
        print("Error occured", ex)
        print(traceback.format_exc())



def log_ui_feature_action(widget, feature):
    text = "###"
    if hasattr(widget, 'currentText'):
        text = widget.currentText()
    if hasattr(widget, 'text'):
        text = widget.text()
    name = feature.name() if hasattr(feature, 'name') else "###"
    log.info("Click on UI %s element for %s", text, name)


def open_web_link():
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(
        "https://github.com/johnfanv2/LenovoLegionLinux"))


def open_star_link():
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(
        "https://github.com/johnfanv2/LenovoLegionLinux"))


class EnumFeatureController:
    widget: QComboBox
    feature: FileFeature
    dependent_controllers: List
    check_after_set_time: float

    def __init__(self, widget: QComboBox, feature: FileFeature):
        self.widget = widget
        self.feature = feature
        self.dependent_controllers = []
        self.check_after_set_time = 0.1
        self.widget.currentIndexChanged.connect(self.on_ui_element_click)

    def on_ui_element_click(self):
        log_ui_feature_action(self.widget, self.feature)
        self.update_feature_from_view()

    def update_feature_from_view(self):
        # print("update_feature_from_view", self.widget.currentText())
        try:
            if self.feature.exists():
                gui_value = self.widget.currentText()
                values = self.feature.get_values()
                value = None
                for val in values:
                    if gui_value == val.name:
                        value = val.value

                if value is not None:
                    print(f"Set to value: {value}")
                    self.feature.set(value)
                else:
                    print(f"Value for gui_value {gui_value} not found")
            else:
                self.widget.setDisabled(True)
        # pylint: disable=broad-except
        except Exception as ex:
            mark_error_combobox(self.widget)
            log_error(ex)
        time.sleep(0.200)
        self.update_view_from_feature()

        if self.dependent_controllers:
            time.sleep(self.check_after_set_time)
            for contr in self.dependent_controllers:
                contr.update_view_from_feature()

    def update_view_from_feature(self, k=0, update_items=False):
        log.info("update_view_from_feature: %d", k)
        try:
            if self.feature.exists():
                # possible values -> items
                values = self.feature.get_values()
                self.widget.blockSignals(True)
                if update_items:
                    self.widget.clear()
                    for val in values:
                        self.widget.addItem(val.name)
                self.widget.blockSignals(False)

                # value -> index
                value = self.feature.get()
                self.widget.blockSignals(True)
                for i, val in enumerate(values):
                    if value == val.value:
                        self.widget.setCurrentIndex(i)
                self.widget.blockSignals(False)
                self.widget.setDisabled(False)
            else:
                self.widget.setDisabled(True)
        # pylint: disable=broad-except
        except Exception as ex:
            mark_error_combobox(self.widget)
            log_error(ex)


class BoolFeatureController:
    checkbox: QCheckBox
    feature: FileFeature
    dependent_controllers: List
    check_after_set_time: float

    def __init__(self, checkbox: QCheckBox, feature: FileFeature):
        self.checkbox = checkbox
        self.feature = feature
        self.checkbox.clicked.connect(self.on_ui_element_click)
        self.dependent_controllers = []
        self.check_after_set_time = 0.1

    def on_ui_element_click(self):
        log_ui_feature_action(self.checkbox, self.feature)
        self.update_feature_from_view()

    def update_feature_from_view(self):
        try:
            if self.feature.exists():
                gui_value = self.checkbox.isChecked()
                self.feature.set(gui_value)
                time.sleep(0.100)
                feature_value = self.feature.get()
                self.checkbox.setChecked(feature_value)
                self.checkbox.setDisabled(False)
            else:
                self.checkbox.setDisabled(True)
        # pylint: disable=broad-except
        except Exception as ex:
            mark_error(self.checkbox)
            log_error(ex)

        if self.dependent_controllers:
            time.sleep(self.check_after_set_time)
            for contr in self.dependent_controllers:
                contr.update_view_from_feature()

    def update_view_from_feature(self):
        try:
            if self.feature.exists():
                feature_value = self.feature.get()
                self.checkbox.setChecked(feature_value)
                self.checkbox.setDisabled(False)
            else:
                self.checkbox.setDisabled(True)
        # pylint: disable=broad-except
        except Exception as ex:
            mark_error(self.checkbox)
            log_error(ex)


class BoolFeatureTrayController:
    action: QAction
    feature: FileFeature
    dependent_controllers: List

    def __init__(self, action: QAction, feature: FileFeature):
        self.action = action
        self.feature = feature
        self.action.setCheckable(True)
        self.action.triggered.connect(self.on_ui_element_click)
        self.dependent_controllers = []

    def on_ui_element_click(self):
        log_ui_feature_action(self.action, self.feature)
        self.update_feature_from_view()

    def update_feature_from_view(self):
        try:
            if self.feature.exists():
                gui_value = self.action.isChecked()
                self.feature.set(gui_value)
        # pylint: disable=broad-except
        except Exception as ex:
            log_error(ex)
        if self.dependent_controllers:
            time.sleep(0.100)
            for contr in self.dependent_controllers:
                contr.update_view_from_feature()

    def update_view_from_feature(self):
        try:
            if self.feature.exists():
                hw_value = self.feature.get()
                self.action.setChecked(hw_value)
                self.action.setDisabled(False)
                self.action.setCheckable(True)
            else:
                self.action.setDisabled(True)
                self.action.setCheckable(False)
        # pylint: disable=broad-except
        except Exception as ex:
            log_error(ex)


class PresetTrayController(QtCore.QObject):
    view_changed = QtCore.pyqtSignal(str)
    action: List[QAction]
    model: LegionModelFacade
    dependent_controllers: List

    def __init__(self, model: LegionModelFacade, actions: List[QAction]):
        super().__init__()
        self.actions = actions
        self.model = model
        self.dependent_controllers = []
        self.update_view_from_feature()

    def update_view_from_feature(self):
        preset_names = list(self.model.fancurve_repo.get_names())
        for i, action in enumerate(self.actions):
            if i < len(preset_names):
                name = preset_names[i]
                action.setVisible(True)
                action.setText(f"Apply preset {name}")
                action.setCheckable(False)
                action.setDisabled(not self.model.fancurve_repo.does_exists_by_name(name))

                # Connect function to set respective preset and
                # take current value of name into closure
                def callback(_, pname = name):
                    self.on_action_click(pname)
                # Disconnect previous if any to avoid multiple connections
                try: 
                    action.triggered.disconnect()
                except: 
                    pass
                action.triggered.connect(callback)
            else:
                action.setVisible(False)

    def on_action_click(self, name):
        log.info("Setting preset %s from tray action", name)
        self.model.fancurve_write_preset_to_hw(name)
        self.view_changed.emit(name)


class EnumFeatureTrayController:
    action: List[QAction]
    feature: FileFeature
    dependent_controllers: List

    def __init__(self, feature: FileFeature, actions: List[QAction]):
        self.actions = actions
        self.feature = feature
        self.dependent_controllers = []
        self.update_view_from_feature(connect=True)

    def update_view_from_feature(self, connect=False):
        log.info("update_view_from_feature in EnumFeatureTrayController ")
        try:
            if self.feature.exists():
                # possible values -> items
                values = self.feature.get_values()
                current_value = self.feature.get()
                # Update each action for each possible value
                for i, action in enumerate(self.actions):
                    if i < len(values):
                        value = values[i].value
                        name = values[i].name
                        action.setVisible(True)
                        action.setText(f"Set {name}")
                        action.setCheckable(True)
                        action.setChecked(value == current_value)

                        if connect:
                            # Connect function to set respective preset and
                            # take current value of name into closure
                            def callback(_, pvalue = value):
                                self.on_action_click(pvalue)
                            action.triggered.connect(callback)
                    else:
                        # there are more actions than values, so hide it
                        action.setVisible(False)
            else:
                for i, action in enumerate(self.actions):
                    if i< len(values):
                        value, name = values[i]
                        action.setText(f"Set {name}")
                        action.setCheckable(True)
                        action.setChecked(False)
                        action.setDisabled(True)
                    else:
                        # there are more actions than values, so hide it
                        action.setVisible(False)
        # pylint: disable=broad-except
        except Exception as ex:
            log_error(ex)

    def on_action_click(self, value):
        log.info("Setting value %s from tray action", value)
        try:
            if self.feature.exists():
                self.feature.set(value)
        # pylint: disable=broad-except
        except Exception as ex:
            log_error(ex)
        time.sleep(0.200)
        log.info("Update view after setting inEnumFeatureTrayController ")
        self.update_view_from_feature()
        if self.dependent_controllers:
            time.sleep(0.100)
            for contr in self.dependent_controllers:
                log.info("Update dependent view %s in EnumFeatureTrayController", str(contr))
                contr.update_view_from_feature()


def set_dependent(controller1, controller2):
    controller1.dependent_controllers.append(controller2)
    controller2.dependent_controllers.append(controller1)


class IntFeatureController:
    widget: QSpinBox
    feature: IntFileFeature

    def __init__(self, widget: QComboBox, feature: FileFeature, update_on_change=False):
        self.widget = widget
        self.feature = feature
        if update_on_change:
            self.widget.valueChanged.connect(self.on_ui_element_click)

    def on_ui_element_click(self):
        log_ui_feature_action(self.widget, self.feature)
        self.update_feature_from_view()

    def update_feature_from_view(self, wait=True):
        # print("update_feature_from_view", self.widget.currentText())
        try:
            if self.feature.exists():
                gui_value = self.widget.value()
                low, upper, _ = self.feature.get_limits_and_step()
                if low <= gui_value <= upper:
                    print(f"Set to value: {gui_value}")
                    self.feature.set(gui_value)
                else:
                    print(
                        f"Value for gui_value {gui_value} not ignored with limits {low} and {upper}")
            else:
                self.widget.setDisabled(True)
        # pylint: disable=broad-except
        except Exception as ex:
            mark_error_combobox(self.widget)
            log_error(ex)
        if wait:
            time.sleep(0.200)
        self.update_view_from_feature()

    def update_view_from_feature(self, k=0, update_bounds=False):
        print("update_view_from_feature", k)
        try:
            if self.feature.exists():
                # possible values
                low, upper, _ = self.feature.get_limits_and_step()
                if update_bounds:
                    self.widget.blockSignals(True)
                    self.widget.setMinimum(low)
                    self.widget.setMaximum(upper)
                    self.widget.blockSignals(False)

                # value -> index
                value = self.feature.get()
                self.widget.blockSignals(True)
                self.widget.setValue(value)
                self.widget.blockSignals(False)
                self.widget.setDisabled(False)
            else:
                self.widget.setDisabled(True)
        # pylint: disable=broad-except
        except Exception as ex:
            mark_error_combobox(self.widget)
            log_error(ex)

class HybridGsyncController:
    gsynchybrid_feature: GsyncFeature
    target_value: Optional[dict]

    def __init__(self, gsynchybrid_feature: GsyncFeature,
                 current_state_label: QLabel,
                 activate_button: QPushButton,
                 deactivate_button: QPushButton):
        self.current_state_label = current_state_label
        self.gsynchybrid_feature = gsynchybrid_feature
        self.target_value = None
        self.activate_button = activate_button
        self.deactivate_button = deactivate_button
        self.activate_button.clicked.connect(self.activate)
        self.deactivate_button.clicked.connect(self.deactivate)

    def activate(self):
        log_ui_feature_action(self.activate_button, self.gsynchybrid_feature)
        self.gsynchybrid_feature.set(True)
        self.target_value = True
        self.update_view_from_feature()

    def deactivate(self):
        log_ui_feature_action(self.deactivate_button, self.gsynchybrid_feature)
        self.gsynchybrid_feature.set(False)
        self.target_value = False
        self.update_view_from_feature()

    def update_feature_from_view(self, _):
        pass

    def update_view_from_feature(self):
        try:
            if not self.gsynchybrid_feature.exists():
                current_val_str = 'no encontrado'
            else:
                value = self.gsynchybrid_feature.get()
                if value:
                    current_val_str = 'actual: activo'
                else:
                    current_val_str = 'actual: inactivo'
        # pylint: disable=broad-except
        except Exception as ex:
            current_val_str = 'error'
            log_error(ex)

        if self.target_value is None:
            target_val_str = ''
        elif self.target_value:
            target_val_str = '- objetivo: activo (requiere reinicio)'
        else:
            target_val_str = '- objetivo: inactivo (requiere reinicio)'
        self.current_state_label.setText(
            current_val_str + ' ' + target_val_str)


class LegionController:
    model: LegionModelFacade
    # fan
    lockfancontroller_controller: BoolFeatureController
    maximumfanspeed_controller: BoolFeatureController
    # other
    fnlock_controller: BoolFeatureController
    winkey_controller: BoolFeatureController
    touchpad_controller: BoolFeatureController
    camera_power_controller: BoolFeatureController
    overdrive_controller: BoolFeatureController
    hybrid_gsync_controller: HybridGsyncController
    batteryconservation_controller: BoolFeatureController
    always_on_usb_controller: BoolFeatureController
    rapid_charging_controller: BoolFeatureController
    power_mode_controller: EnumFeatureController
    # tray
    batteryconservation_tray_controller: BoolFeatureTrayController
    rapid_charging_tray_controller: BoolFeatureTrayController
    fnlock_tray_controller: BoolFeatureTrayController
    touchpad_tray_controller: BoolFeatureTrayController
    always_on_usb_tray_controller: BoolFeatureTrayController
    power_mode_tray_controller: EnumFeatureTrayController
    preset_tray_controller: PresetTrayController

    def __init__(self, app:QApplication, expect_hwmon=True, use_legion_cli_to_write=False, config_dir=None):
        self.model = LegionModelFacade(
            expect_hwmon=expect_hwmon, use_legion_cli_to_write=use_legion_cli_to_write, config_dir=config_dir)
        self.app = app
        self.view_dashboard = None
        self.view_fancurve = None
        self.view_otheroptions = None
        self.main_window = None
        self.tray = None
        self.show_root_dialog = (not self.model.is_root_user()) and (
            not use_legion_cli_to_write)
        self.monitoring_threadpool = QThreadPool()
        self.monitoring_worker = MonitorWorker(None)

        # tray
        self.batteryconservation_tray_controller = None
        self.rapid_charging_tray_controller = None
        self.fnlock_tray_controller = None
        self.touchpad_tray_controller = None
        self.always_on_usb_tray_controller = None
        self.power_mode_tray_controller = None
        self.preset_tray_controller = None
        
        self.monitoring_threadpool = QThreadPool()
        self.monitoring_worker = MonitorWorker(None)

    def init(self, read_from_hw=True):
        print("DEBUG: LegionController.init started")
        if not hasattr(self, 'show_root_dialog'):
            self.show_root_dialog = False
        # connect logger output to GUI
        # qt_handler.qt_obj.logWritten.connect(self.on_new_log_msg)

        print("DEBUG: Setting monitoring worker model")
        self.monitoring_worker.model = self.model
        # Connect monitoring signals to Dashboard
        print(f"DEBUG: view_dashboard is {self.view_dashboard}")
        if self.view_dashboard:
            print("DEBUG: Connecting update_stats")
            self.monitoring_worker.signals.statsUpdated.connect(self.view_dashboard.update_stats)
        else:
            print("ERROR: view_dashboard is None!")
        
        print("DEBUG: Finished connecting statsUpdated")

        # fan
        self.lockfancontroller_controller = BoolFeatureController(
            self.view_fancurve.lockfancontroller_check,
            self.model.lockfancontroller)
        self.maximumfanspeed_controller = BoolFeatureController(
            self.view_fancurve.maximumfanspeed_check,
            self.model.maximum_fanspeed)
        # other
        self.fnlock_controller = BoolFeatureController(
            self.view_otheroptions.fnlock_check,
            self.model.fn_lock)
        self.winkey_controller = BoolFeatureController(
            self.view_otheroptions.winkey_check,
            self.model.winkey)
        self.touchpad_controller = BoolFeatureController(
            self.view_otheroptions.touchpad_check,
            self.model.touchpad)
        self.camera_power_controller = BoolFeatureController(
            self.view_otheroptions.camera_power_check,
            self.model.camera_power)
        self.overdrive_controller = BoolFeatureController(
            self.view_otheroptions.overdrive_check,
            self.model.overdrive)
        self.batteryconservation_controller = BoolFeatureController(
            self.view_otheroptions.batteryconservation_check,
            self.model.battery_conservation)
        self.rapid_charging_controller = BoolFeatureController(
            self.view_otheroptions.rapid_charging_check,
            self.model.rapid_charging)
        self.batteryconservation_controller.dependent_controllers.append(
            self.rapid_charging_controller)
        self.rapid_charging_controller.dependent_controllers.append(
            self.batteryconservation_controller)
        self.always_on_usb_controller = BoolFeatureController(
            self.view_otheroptions.always_on_usb_check,
            self.model.always_on_usb_charging)
        self.power_mode_controller = EnumFeatureController(
            self.view_otheroptions.power_mode_combo,
            self.model.platform_profile
        )
        self.hybrid_gsync_controller = HybridGsyncController(
            gsynchybrid_feature=self.model.gsync,
            current_state_label=self.view_otheroptions.hybrid_state_label,
            activate_button=self.view_otheroptions.hybrid_activate_button,
            deactivate_button=self.view_otheroptions.hybrid_deactivate_button)


        # settings callback
        self.model.app_model.enable_gui_monitoring.add_callback(self.on_enable_monitoring_change)

        if read_from_hw:
            print("DEBUG: Reading from hw (async)")
            import threading
            threading.Thread(target=self.on_read_fan_curve_from_hw, daemon=True).start()
            # log.warning("HW Fan Curve reading DISABLED for debugging.")
            # self.model.read_fancurve_from_hw()
            # fan controller
        # fan
        self.update_fancurve_gui()
        self.update_fan_additional_gui()
        self.update_other_gui()
        self.update_power_gui(True)
        # log.warning("Initial GUI updates DISABLED for debugging.")
        self.view_fancurve.set_presets(self.model.fancurve_repo.get_names())
        self.main_window.show_root_dialog = self.show_root_dialog
        self.start_monitoring()
        # log.warning("Monitoring DISABLED for debugging.")

    def init_tray(self):
        print("DEBUG: LegionController.init_tray started")
        
        # Hard disable tray to prevent Segfaults on systems with broken DBus/Tray support
        log.warning("Tray icon disabled for stability.")
        self.tray = None
        return

        # if not QSystemTrayIcon.isSystemTrayAvailable():
        #      log.warning("System tray is not available. Skipping tray icon creation.")
        #      self.tray = None
        #      return

        try:
            self.tray = LegionTray(
                self.main_window.icon, self.main_window, self)
        except Exception as e:
            log.error(f"Failed to initialize system tray: {e}")
            self.tray = None
            return

        # tray/other
        self.batteryconservation_tray_controller = BoolFeatureTrayController(
            self.tray.batteryconservation_action, self.model.battery_conservation)
        set_dependent(self.batteryconservation_controller,
                      self.batteryconservation_tray_controller)
        set_dependent(self.rapid_charging_controller,
                      self.batteryconservation_tray_controller)
        self.batteryconservation_tray_controller.update_view_from_feature()

        self.rapid_charging_tray_controller = BoolFeatureTrayController(
            self.tray.rapid_charging_action, self.model.rapid_charging)
        set_dependent(self.batteryconservation_controller,
                      self.rapid_charging_tray_controller)
        set_dependent(self.rapid_charging_controller,
                      self.rapid_charging_tray_controller)
        set_dependent(self.batteryconservation_tray_controller,
                      self.rapid_charging_tray_controller)
        self.rapid_charging_tray_controller.update_view_from_feature()
        print("DEBUG: init_tray - charging controllers initialized")

        self.fnlock_tray_controller = BoolFeatureTrayController(
            self.tray.fnlock_action, self.model.fn_lock)
        set_dependent(self.fnlock_tray_controller, self.fnlock_controller)
        self.fnlock_tray_controller.update_view_from_feature()

        self.touchpad_tray_controller = BoolFeatureTrayController(
            self.tray.touchpad_action, self.model.touchpad)
        set_dependent(self.touchpad_tray_controller, self.touchpad_controller)
        self.touchpad_tray_controller.update_view_from_feature()

        self.always_on_usb_tray_controller = BoolFeatureTrayController(
            self.tray.always_on_usb_charging_action, self.model.always_on_usb_charging)
        set_dependent(self.always_on_usb_tray_controller, self.always_on_usb_controller)
        self.always_on_usb_tray_controller.update_view_from_feature()
        self.power_mode_tray_controller = EnumFeatureTrayController(self.model.platform_profile,
            [self.tray.powermode1_action,
             self.tray.powermode2_action,
             self.tray.powermode3_action,
             self.tray.powermode4_action])
        set_dependent(self.power_mode_tray_controller, self.power_mode_controller)
        self.power_mode_tray_controller.update_view_from_feature()

        try:
            self.preset_tray_controller = PresetTrayController(self.model,
                [self.tray.preset1_action,
                 self.tray.preset2_action,
                 self.tray.preset3_action])
            
            # Connect signals
            self.preset_tray_controller.view_changed.connect(self.on_load_from_preset)
        except Exception as e:
            log.error(f"Error initializing preset controller: {e}")

    def update_fan_additional_gui(self):
        self.lockfancontroller_controller.update_view_from_feature()
        self.maximumfanspeed_controller.update_view_from_feature()

    def update_other_gui(self):
        self.fnlock_controller.update_view_from_feature()
        self.winkey_controller.update_view_from_feature()
        self.touchpad_controller.update_view_from_feature()
        self.camera_power_controller.update_view_from_feature()
        self.batteryconservation_controller.update_view_from_feature()
        self.rapid_charging_controller.update_view_from_feature()
        self.always_on_usb_controller.update_view_from_feature()
        self.overdrive_controller.update_view_from_feature()
        self.hybrid_gsync_controller.update_view_from_feature()

    def update_power_gui(self, update_bounds=False):
        self.power_mode_controller.update_view_from_feature(
            0, update_items=update_bounds)

    def power_gui_write_to_hw(self):
        self.update_power_gui()

    def update_fancurve_gui(self):
        self.view_fancurve.set_fancurve(self.model.fan_curve,
                                        self.model.fancurve_io.has_minifancurve(),
                                        self.model.fancurve_io.exists())

    # Removed update_automation for simplification

    def on_read_fan_curve_from_hw(self):
        log.info("Reading fan curve from HW (background thread)...")
        try:
            self.model.read_fancurve_from_hw()
            # Marshal UI update to main thread
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            # QMetaObject.invokeMethod(self.app, "processEvents", Qt.ConnectionType.QueuedConnection)
            # Alternatively, use a signal or QTimer, but let's try to schedule the update on the main thread loop
            # Since self is LegionController (not a QObject), we can't invoke directly on it easily if it doesn't inherit QObject
            # But earlier code shows it does NOT inherit QObject. 
            # However, self.view_fancurve IS a QWidget.
            
            QMetaObject.invokeMethod(self.view_fancurve, "update_fancurve_gui", Qt.ConnectionType.QueuedConnection)
            log.info("Scheduled update_fancurve_gui on main thread")
        except Exception as e:
            log.error(f"Error reading fan curve from HW: {e}")

    def on_write_fan_curve_to_hw(self):
        # Debugging
        print("DEBUG: on_write_fan_curve_to_hw called")
        self.model.fan_curve = self.view_fancurve.get_fancurve()
        self.model.write_fancurve_to_hw()
        self.model.read_fancurve_from_hw()
        self.update_fancurve_gui()
    def on_load_from_preset(self, name=None):
        if not name or isinstance(name, bool):
            name = self.view_fancurve.preset_combobox.currentText()
        log.info("Loading preset: %s", name)
        try:
            self.model.load_fancurve_from_preset(name)
            self.update_fancurve_gui()
        except Exception as e:
            log.error("Could not load preset %s: %s", name, str(e))

    def on_save_to_preset(self, _=None):
        name = self.view_fancurve.preset_combobox.currentText()
        log.info("Saving preset: %s", name)
        
        self.model.fan_curve = self.view_fancurve.get_fancurve()
        try:
            self.model.save_fancurve_to_preset(name)
        except Exception as e:
            log.error(f"Could not save preset {name}: {e}")



    def save_settings(self):
        try:
            self.model.save_settings()
            if self.view_fancurve:
                name = self.view_fancurve.preset_combobox.currentText()
                self.model.fan_curve = self.view_fancurve.get_fancurve()
                self.model.save_fancurve_to_preset(name)
                self.model.write_fancurve_to_hw()
                log.info(f"Saved and applied FanCurve for preset: {name}")
        except PermissionError as err:
            log_error(err)

    def apply_theme(self, theme_value):
        """Apply a theme and persist the setting."""
        self.model.app_model.gui_theme.set(theme_value)
        resolved = self._resolve_theme(theme_value)
        self.app.setStyleSheet(get_stylesheet(resolved))
        self.model.save_settings()

    def _resolve_theme(self, theme_value):
        """Resolve 'auto' to an actual dark/light value."""
        if theme_value == 'auto':
            detected = get_color_mode()
            return detected if detected in ('dark', 'light') else 'dark'
        return theme_value

    def init_theme_from_settings(self):
        """Initialize the theme combo and apply the persisted theme."""
        theme_value = self.model.app_model.gui_theme.get()
        if self.view_otheroptions:
            self.view_otheroptions.set_theme_combo_value(theme_value)
        resolved = self._resolve_theme(theme_value)
        self.app.setStyleSheet(get_stylesheet(resolved))

    def app_close_and_save(self):
        self.stop_monitoring()
        self.save_settings()
        self.app.quit()

    def app_close(self):
        self.stop_monitoring()
        self.app.quit()

    def app_show(self):
        self.main_window.bring_to_foreground()

    def start_monitoring(self):
        log.info("Starting monitoring")
        if not self.monitoring_worker.running:
            self.monitoring_worker = MonitorWorker(self.model)
            # Reconnect signals as they were lost with the new worker
            self.monitoring_worker.signals.statsUpdated.connect(self.view_dashboard.update_stats)
            self.monitoring_worker.running = True
            self.monitoring_threadpool.start(self.monitoring_worker)

    def stop_monitoring(self):
        log.info("Stopping monitoring")
        self.monitoring_worker.running = False

    def on_enable_monitoring_change(self, _):
        if self.model.app_model.enable_gui_monitoring.get():
            # self.start_monitoring()
            log.warning("Monitoring callback DISABLED for debugging.")
        else:
            self.stop_monitoring()


class FanCurveEntryView(QtCore.QObject):
    tempChanged = QtCore.pyqtSignal(int, int) # point_id, new_temp_index (0=cpu, 1=gpu, 2=ic)
    
    # Predefined discrete values as requested
    RPM_VALUES = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500]
    TEMP_VALUES = [0, 20, 30, 40, 50, 60, 70, 80, 90, 100]

    def __init__(self, point_id, layout, parent_tab):
        super().__init__()
        self.point_id = point_id
        self.parent_tab = parent_tab
        self.point_id_label = QLabel(f'{point_id}')
        self.point_id_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.point_id_label.setStyleSheet("font-weight: bold; color: #aaa;")
        
        self.fan_speed1_combo = self._create_combo(self.RPM_VALUES)
        self.fan_speed2_combo = self._create_combo(self.RPM_VALUES)
        self.cpu_temp_combo = self._create_combo(self.TEMP_VALUES)
        self.gpu_temp_combo = self._create_combo(self.TEMP_VALUES)
        self.ic_temp_combo = self._create_combo(self.TEMP_VALUES)

        layout.addWidget(self.point_id_label, 1, point_id)
        layout.addWidget(self.fan_speed1_combo, 2, point_id)
        layout.addWidget(self.fan_speed2_combo, 3, point_id)
        layout.addWidget(self.cpu_temp_combo, 4, point_id)
        layout.addWidget(self.gpu_temp_combo, 5, point_id)
        layout.addWidget(self.ic_temp_combo, 6, point_id)

    def _create_combo(self, values):
        combo = QComboBox()
        combo.addItems([str(v) for v in values])
        combo.setEditable(False) # Strict selection only
        # Connect signal
        combo.currentIndexChanged.connect(self.on_value_changed)
        # Style to look minimal but clear
        combo.setStyleSheet("""
            QComboBox {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 2px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                selection-background-color: #444;
                color: #e0e0e0;
            }
        """)
        return combo

    def on_value_changed(self):
        self.parent_tab.refresh_graph()

    def _set_combo_value(self, combo, value, values_list):
        # Find closest value in list to handle legacy data or mismatches
        closest_val = min(values_list, key=lambda x: abs(x - value))
        try:
            index = values_list.index(closest_val)
            combo.setCurrentIndex(index)
        except ValueError:
             combo.setCurrentIndex(0)

    def _get_combo_value(self, combo):
        try:
            return int(combo.currentText())
        except ValueError:
            return 0

    def set(self, entry: FanCurveEntry):
        # Block signals during batch update to prevent flicker
        self.fan_speed1_combo.blockSignals(True)
        self.fan_speed2_combo.blockSignals(True)
        self.cpu_temp_combo.blockSignals(True)
        self.gpu_temp_combo.blockSignals(True)
        self.ic_temp_combo.blockSignals(True)
        
        self._set_combo_value(self.fan_speed1_combo, int(entry.fan1_speed), self.RPM_VALUES)
        self._set_combo_value(self.fan_speed2_combo, int(entry.fan2_speed), self.RPM_VALUES)
        self._set_combo_value(self.cpu_temp_combo, int(entry.cpu_upper_temp), self.TEMP_VALUES)
        self._set_combo_value(self.gpu_temp_combo, int(entry.gpu_upper_temp), self.TEMP_VALUES)
        self._set_combo_value(self.ic_temp_combo, int(entry.ic_upper_temp), self.TEMP_VALUES)
        
        self.fan_speed1_combo.blockSignals(False)
        self.fan_speed2_combo.blockSignals(False)
        self.cpu_temp_combo.blockSignals(False)
        self.gpu_temp_combo.blockSignals(False)
        self.ic_temp_combo.blockSignals(False)

    def set_disabled(self, value: bool):
        self.fan_speed1_combo.setDisabled(value)
        self.fan_speed2_combo.setDisabled(value)
        self.cpu_temp_combo.setDisabled(value)
        self.gpu_temp_combo.setDisabled(value)
        self.ic_temp_combo.setDisabled(value)

    def get(self) -> FanCurveEntry:
        return FanCurveEntry(
            fan1_speed=self._get_combo_value(self.fan_speed1_combo),
            fan2_speed=self._get_combo_value(self.fan_speed2_combo),
            cpu_lower_temp=self._get_combo_value(self.cpu_temp_combo) - 5,
            cpu_upper_temp=self._get_combo_value(self.cpu_temp_combo),
            gpu_lower_temp=self._get_combo_value(self.gpu_temp_combo) - 5,
            gpu_upper_temp=self._get_combo_value(self.gpu_temp_combo),
            ic_lower_temp=self._get_combo_value(self.ic_temp_combo) - 5,
            ic_upper_temp=self._get_combo_value(self.ic_temp_combo),
            acceleration=self.parent_tab.global_accel_spin.value(),
            deceleration=self.parent_tab.global_decel_spin.value()
        )


class FanCurveGraph(QWidget):
    pointDragged = QtCore.pyqtSignal(int, int) # point_id (1-10), rpm

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.entries = []
        self.points = []
        self.dragging_idx = -1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def update_data(self, entries):
        self.entries = entries
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            w = self.width()
            col_w = w / 10
            idx = int(event.pos().x() / col_w)
            if 0 <= idx < len(self.entries):
                self.dragging_idx = idx
                self.update_drag(event.pos().y())

    def mouseMoveEvent(self, event):
        if self.dragging_idx != -1:
            self.update_drag(event.pos().y())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging_idx = -1

    def update_drag(self, mouse_y):
        h = self.height()
        y = max(0, min(h, mouse_y))
        raw_rpm = int((1 - y / h) * 4500)
        
        # Snap to nearest 500 (RPM Values from FanCurveEntryView)
        # Using a simpler logic here to avoid circular dependency import issues if class access is tricky
        rpm_values = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500]
        closest_rpm = min(rpm_values, key=lambda x: abs(x - raw_rpm))
        
        self.pointDragged.emit(self.dragging_idx + 1, closest_rpm)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor("#121212") if self.palette().window().color().lightness() < 128 else QColor("#FFFFFF"))
        
        # Draw Grid
        painter.setPen(QColor(100, 100, 100, 50))
        w, h = self.width(), self.height()
        
        # Horizontal lines (10 levels)
        for i in range(11):
            y = int(i * h / 10)
            painter.drawLine(0, y, w, y)
        
        # Vertical lines (10 points)
        for i in range(11):
            x = int(i * w / 10)
            painter.drawLine(x, 0, x, h)

        if not self.entries:
            return

        # Draw Curves
        # Fan 1: Cyan, Fan 2: Pink
        self.draw_curve(painter, 1, QColor("#43D2DE"))
        self.draw_curve(painter, 2, QColor("#E54297"))

    def draw_curve(self, painter, fan_idx, color):
        w, h = self.width(), self.height()
        path = QPainterPath()
        started = False
        
        painter.setPen(QPen(color, 2))
        
        # Align points with 10 columns
        col_w = w / 10
        
        for i, e in enumerate(self.entries):
            # Point alignment: center of the column
            x = int((i + 0.5) * col_w)
            # Y mapping: 0-4500 RPM
            speed = e.fan1_speed if fan_idx == 1 else e.fan2_speed
            y = h - int(speed * h / 4500)
            
            if not started:
                path.moveTo(x, y)
                started = True
            else:
                path.lineTo(x, y)
            painter.drawEllipse(x-3, y-3, 6, 6)
        
        painter.drawPath(path)


class FanCurveTab(QWidget):
    def __init__(self, controller: LegionController):
        super().__init__()
        self.controller = controller
        self.entry_edits = []
        self.init_ui()

        self.controller.view_fancurve = self

    @pyqtSlot()
    def update_fancurve_gui(self):
        self.controller.update_fancurve_gui()

    def set_fancurve(self, fancurve: FanCurve, has_minifancurve: bool, enabled: bool):
        self.minfancurve_check.setDisabled(not has_minifancurve)
        for i, entry in enumerate(fancurve.entries):
            self.entry_edits[i].set(entry)
            self.entry_edits[i].set_disabled(not enabled)
        
        # Set global accel from the first entry if available
        if fancurve.entries:
            self.global_accel_spin.setValue(fancurve.entries[0].acceleration)
            self.global_decel_spin.setValue(fancurve.entries[0].deceleration)

        self.load_button.setDisabled(not enabled)
        self.write_button.setDisabled(not enabled)
        self.minfancurve_check.setChecked(fancurve.enable_minifancurve)
        self.refresh_graph()

    def refresh_graph(self):
        fc = self.get_fancurve()
        self.graph.update_data(fc.entries)

    def on_graph_point_dragged(self, point_id, rpm):
        idx = point_id - 1
        if 0 <= idx < len(self.entry_edits):
            view = self.entry_edits[idx]
            # Block signals to prevent infinite recursion refreshing the graph
            view.fan_speed1_combo.blockSignals(True)
            view.fan_speed2_combo.blockSignals(True)
            
            view._set_combo_value(view.fan_speed1_combo, rpm, view.RPM_VALUES)
            view._set_combo_value(view.fan_speed2_combo, rpm, view.RPM_VALUES)
            
            view.fan_speed1_combo.blockSignals(False)
            view.fan_speed2_combo.blockSignals(False)

            self.refresh_graph()

    def get_fancurve(self) -> FanCurve:
        entries = []
        g_accel = self.global_accel_spin.value()
        g_decel = self.global_decel_spin.value()
        for i in range(10):
            entry = self.entry_edits[i].get()
            entries.append(entry)
        return FanCurve(name='unknown', entries=entries,
                        enable_minifancurve=self.minfancurve_check.isChecked())

    def create_fancurve_entry_view(self, layout, point_id):
        view = FanCurveEntryView(point_id, layout, self)
        self.entry_edits.append(view)

    def on_temp_changed(self, point_id, temp_type):
        self.refresh_graph()

    def set_presets(self, presets):
        self.preset_combobox.blockSignals(True)
        self.preset_combobox.clear()
        self.preset_combobox.addItems(list(presets))
        self.preset_combobox.blockSignals(False)

    def update_active_profile(self, profile):
        profile = profile.strip().lower()
        self.preset_combobox.blockSignals(True)
        for i in range(self.preset_combobox.count()):
            if profile in self.preset_combobox.itemText(i).lower():
                self.preset_combobox.setCurrentIndex(i)
                break
        self.preset_combobox.blockSignals(False)

    def init_ui(self):
        # pylint: disable=too-many-statements
        self.fancurve_group = QGroupBox("Editor de Curva de Ventiladores")
        self.layout = QGridLayout()
        
        # Add Graph in the grid spanning 10 columns
        self.graph = FanCurveGraph()
        self.graph.pointDragged.connect(self.on_graph_point_dragged)
        self.layout.addWidget(self.graph, 0, 1, 1, 10)
        # log.warning("FanCurveGraph DISABLED for debugging.")
        
        self.point_id_label = QLabel("Punto")
        self.fan_speed1_label = QLabel("Ventilador 1 [rpm]")
        self.fan_speed2_label = QLabel("Ventilador 2 [rpm]")
        self.cpu_temp_label = QLabel("Temp. CPU [°C]")
        self.gpu_temp_label = QLabel("Temp. GPU [°C]")
        self.ic_temp_label = QLabel("Temp. IC [°C]")
        
        self.global_accel_label = QLabel("Aceleración Global [s]")
        self.global_accel_spin = MinimalistSpinBox()
        self.global_accel_spin.setRange(1, 10)
        
        self.global_decel_label = QLabel("Desaceleración Global [s]")
        self.global_decel_spin = MinimalistSpinBox()
        self.global_decel_spin.setRange(1, 10)

        self.minfancurve_check = QCheckBox("Apagar ventiladores si está frío")
        self.lockfancontroller_check = QCheckBox(
            "Bloquear controlador, sensores y velocidad actual")
        self.maximumfanspeed_check = QCheckBox(
            "Forzar Velocidad Máxima")
        
        # Labels column
        self.layout.addWidget(self.point_id_label, 1, 0)
        self.layout.addWidget(self.fan_speed1_label, 2, 0)
        self.layout.addWidget(self.fan_speed2_label, 3, 0)
        self.layout.addWidget(self.cpu_temp_label, 4, 0)
        self.layout.addWidget(self.gpu_temp_label, 5, 0)
        self.layout.addWidget(self.ic_temp_label, 6, 0)
        
        # Set column stretch for 100% width
        self.layout.setColumnStretch(0, 0) # Label column
        for i in range(1, 11):
            self.layout.setColumnStretch(i, 1) # Points columns

        for i in range(1, 11):
            self.create_fancurve_entry_view(self.layout, i)
        
        # Unified Controls
        self.extra_options_layout = QHBoxLayout()
        self.extra_options_layout.addWidget(self.global_accel_label)
        self.extra_options_layout.addWidget(self.global_accel_spin)
        self.extra_options_layout.addWidget(self.global_decel_label)
        self.extra_options_layout.addWidget(self.global_decel_spin)
        self.extra_options_layout.addStretch()

        self.main_fancurve_layout = QVBoxLayout()

        self.main_fancurve_layout.addLayout(self.layout)
        
        # Merge Extra Options and Checkboxes into a compact layout
        self.config_row = QHBoxLayout()
        self.config_row.addWidget(self.global_accel_label)
        self.config_row.addWidget(self.global_accel_spin)
        self.config_row.addWidget(self.global_decel_label)
        self.config_row.addWidget(self.global_decel_spin)
        self.config_row.addSpacing(20)
        self.config_row.addWidget(self.minfancurve_check)
        self.config_row.addWidget(self.lockfancontroller_check)
        self.config_row.addWidget(self.maximumfanspeed_check)
        self.config_row.addStretch()
        
        self.main_fancurve_layout.addLayout(self.config_row)
        self.fancurve_group.setLayout(self.main_fancurve_layout)

        # Merge Hardware and Preset into one horizontal "Action Row"
        self.action_group = QGroupBox("Hardware y Preajustes")
        
        # HW Section
        self.load_button = QPushButton("Leer HW")
        self.write_button = QPushButton("Aplicar HW")
        self.load_button.clicked.connect(self.controller.on_read_fan_curve_from_hw)
        self.write_button.clicked.connect(self.controller.on_write_fan_curve_to_hw)
        
        # Preset Section
        self.preset_combobox = QComboBox(self)
        self.preset_combobox.setMinimumWidth(150)
        self.preset_combobox.setEditable(False)

        self.save_to_preset_button = QPushButton("Guardar Preajuste")
        self.load_from_preset_button = QPushButton("Cargar Preajuste")
        self.save_to_preset_button.clicked.connect(self.controller.on_save_to_preset)
        self.load_from_preset_button.clicked.connect(self.controller.on_load_from_preset)

        self.action_layout = QGridLayout()
        self.action_layout.setColumnStretch(0, 1)
        self.action_layout.setColumnStretch(1, 0) # Middle item
        self.action_layout.setColumnStretch(2, 1)
        
        # Left buttons container
        self.left_actions = QHBoxLayout()
        self.left_actions.addStretch()
        self.left_actions.addWidget(self.load_button)
        self.left_actions.addWidget(self.write_button)
        
        # Right buttons container
        self.right_actions = QHBoxLayout()
        self.right_actions.addWidget(self.save_to_preset_button)
        self.right_actions.addWidget(self.load_from_preset_button)
        self.right_actions.addStretch()

        self.action_layout.addLayout(self.left_actions, 0, 0)
        self.action_layout.addWidget(self.preset_combobox, 0, 1, Qt.AlignmentFlag.AlignCenter)
        self.action_layout.addLayout(self.right_actions, 0, 2)
        
        self.action_group.setLayout(self.action_layout)

        self.main_layout = QVBoxLayout()
        self.main_layout.addWidget(self.fancurve_group, 1) # Give more space to editor
        self.main_layout.addWidget(self.action_group, 0)
        self.main_layout.addWidget(QLabel("La curva de ventiladores se reinicia al cambiar el modo de energía (Fn + Q)."), 0)
        
        self.setLayout(self.main_layout)


class OtherOptionsTab(QWidget):
    def __init__(self, controller: LegionController):
        super().__init__()
        self.controller = controller
        self.init_ui()
        self.controller.view_otheroptions = self

    def init_ui(self):
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(15)

        # --- Hidden widgets (still needed by controllers, but not displayed) ---
        # General Settings controls: kept for BoolFeatureController compatibility
        self.fnlock_check = QCheckBox("Bloqueo Fn (Teclas Fn sin presionar Fn)")
        self.touchpad_check = QCheckBox("Touchpad Habilitado")
        self.camera_power_check = QCheckBox("Cámara Habilitada")
        self.winkey_check = QCheckBox("Tecla Win Habilitada")

        # System Performance controls: user uses Fn+Q instead
        self.power_mode_label = QLabel("Modo de Energía / Perfil:")
        self.power_mode_combo = QComboBox()
        self.power_load_button = QPushButton("Leer de HW")
        self.power_write_button = QPushButton("Aplicar a HW")
        self.power_load_button.clicked.connect(self.controller.update_power_gui)
        self.power_write_button.clicked.connect(self.controller.power_gui_write_to_hw)

        # --- 1. Power & Battery ---
        self.battery_group = QGroupBox("Energía y Batería")
        battery_layout = QGridLayout()
        battery_layout.setColumnStretch(0, 1)
        battery_layout.setColumnStretch(1, 1)

        self.rapid_charging_check = QCheckBox("Carga Rápida")
        self.batteryconservation_check = QCheckBox("Conservación de Batería (Límite 60%)")
        self.always_on_usb_check = QCheckBox("Carga USB Siempre Activa")

        battery_layout.addWidget(self.rapid_charging_check, 0, 0, Qt.AlignmentFlag.AlignCenter)
        battery_layout.addWidget(self.batteryconservation_check, 0, 1, Qt.AlignmentFlag.AlignCenter)
        battery_layout.addWidget(self.always_on_usb_check, 1, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)
        self.battery_group.setLayout(battery_layout)

        # --- 2. Display & Graphics ---
        self.display_group = QGroupBox("Pantalla y Gráficos")
        display_layout = QVBoxLayout()

        self.overdrive_check = QCheckBox("Overdrive de Pantalla (Menor Tiempo de Respuesta)")
        
        self.hybrid_label = QLabel("Modo Híbrido:")
        self.hybrid_state_label = QLabel("")
        self.hybrid_activate_button = QPushButton("Activar")
        self.hybrid_deactivate_button = QPushButton("Desactivar")

        hybrid_container = QHBoxLayout()
        hybrid_container.addStretch()
        hybrid_container.addWidget(self.hybrid_label)
        hybrid_container.addWidget(self.hybrid_activate_button)
        hybrid_container.addWidget(self.hybrid_deactivate_button)
        hybrid_container.addWidget(self.hybrid_state_label)
        hybrid_container.addStretch()

        overdrive_container = QHBoxLayout()
        overdrive_container.addStretch()
        overdrive_container.addWidget(self.overdrive_check)
        overdrive_container.addStretch()

        display_layout.addLayout(overdrive_container)
        display_layout.addLayout(hybrid_container)
        self.display_group.setLayout(display_layout)

        # --- 3. Appearance ---
        self.appearance_group = QGroupBox("Apariencia")
        appearance_layout = QHBoxLayout()
        appearance_layout.addStretch()

        self.theme_label = QLabel("Tema:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Auto (Sistema)", "auto")
        self.theme_combo.addItem("Oscuro", "dark")
        self.theme_combo.addItem("Claro", "light")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        appearance_layout.addWidget(self.theme_label)
        appearance_layout.addWidget(self.theme_combo)
        appearance_layout.addStretch()
        self.appearance_group.setLayout(appearance_layout)

        # Add visible groups to main layout, centered
        self.main_layout.addStretch()
        self.main_layout.addWidget(self.battery_group)
        self.main_layout.addWidget(self.display_group)
        self.main_layout.addWidget(self.appearance_group)
        self.main_layout.addStretch()
        self.setLayout(self.main_layout)

    def set_theme_combo_value(self, theme_value):
        """Set the combo box to match a theme value without triggering the change signal."""
        self.theme_combo.blockSignals(True)
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == theme_value:
                self.theme_combo.setCurrentIndex(i)
                break
        self.theme_combo.blockSignals(False)

    def _on_theme_changed(self, index):
        theme_value = self.theme_combo.itemData(index)
        if theme_value and self.controller:
            self.controller.apply_theme(theme_value)





# --- Enhanced Dashboard Components ---

class AnimatedProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.animation = QtCore.QPropertyAnimation(self, b"value")
        self.animation.setDuration(1200) # Slower smooth transition
        self.animation.setEasingCurve(QtCore.QEasingCurve.Type.InOutCubic)

    def setValueSmooth(self, value):
        if self.value() != value:
            self.animation.stop()
            self.animation.setStartValue(self.value())
            self.animation.setEndValue(value)
            self.animation.start()
        else:
            # If same value, ensure it renders
            super().setValue(value)


class SystemStats:
    def __init__(self):
        self.last_cpu_total = 0
        self.last_cpu_idle = 0
        self.init_cpu_stats()

    def init_cpu_stats(self):
        try:
            with open('/proc/stat', 'r') as f:
                line = f.readline()
                parts = line.split()
                # user, nice, system, idle, iowait, irq, softirq, steal
                self.last_cpu_idle = float(parts[4])
                self.last_cpu_total = sum([float(x) for x in parts[1:]])
        except Exception:
            pass

    def get_cpu_usage(self):
        try:
            with open('/proc/stat', 'r') as f:
                line = f.readline()
                parts = line.split()
                idle = float(parts[4])
                total = sum([float(x) for x in parts[1:]])
                
                diff_idle = idle - self.last_cpu_idle
                diff_total = total - self.last_cpu_total
                
                self.last_cpu_idle = idle
                self.last_cpu_total = total
                
                if diff_total == 0: return 0.0
                usage = (1.0 - diff_idle / diff_total) * 100.0
                return round(usage, 1)
        except Exception:
            return 0.0

    def get_ram_usage(self):
        # Returns (percent, used_gb, total_gb)
        try:
            meminfo = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = int(parts[1].strip().split()[0])
            
            total = meminfo.get('MemTotal', 1)
            available = meminfo.get('MemAvailable', 0)
            used = total - available
            percent = (used / total) * 100.0
            return round(percent, 1), round(used / 1024 / 1024, 1), round(total / 1024 / 1024, 1)
        except Exception:
            return 0.0, 0.0, 0.0

    def get_gpu_usage(self):
        # Returns (usage_percent, memory_used_mb)
        # Using nvidia-smi if available
        try:
            import subprocess
            # Query utilization.gpu and memory.used
            result = subprocess.check_output(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader,nounits'], encoding='utf-8')
            parts = result.strip().split(',')
            if len(parts) >= 2:
                return float(parts[0]), float(parts[1])
        except Exception:
            pass
        return 0.0, 0.0


class RealtimeGraph(QWidget):
    def __init__(self, title, labels, colors, max_value=100, unit="", parent=None):
        super().__init__(parent)
        self.title = title
        self.labels = labels
        self.colors = colors # List of QColor
        self.max_value = max_value
        self.unit = unit
        self.data_history = [[] for _ in range(len(labels))] # List of lists
        self.history_size = 60 # Keep 60 points
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def add_data(self, values: List[float]):
        for i, val in enumerate(values):
            if i < len(self.data_history):
                self.data_history[i].append(val)
                if len(self.data_history[i]) > self.history_size:
                    self.data_history[i].pop(0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        
        # Background
        painter.fillRect(self.rect(), QColor("#121212"))
        
        # Title
        painter.setPen(QColor("#ffffff"))
        painter.drawText(10, 20, self.title)

        # Legend
        legend_x = w - 150
        for i, label in enumerate(self.labels):
            painter.setPen(self.colors[i])
            painter.drawText(legend_x, 20 + (i * 15), f"■ {label}")

        # Grid & Labels
        painter.setPen(QColor(100, 100, 100, 50))
        
        # Margins based on text width (approx 30px for labels)
        left_margin = 35
        right_margin = 10
        top_margin = 30
        bottom_margin = 20
        graph_w = w - left_margin - right_margin
        graph_h = h - top_margin - bottom_margin

        # Draw 5 horizontal lines and Y-axis labels
        painter.setFont(QtGui.QFont("Arial", 8))
        for i in range(5):
            y_ratio = i / 4.0
            y = int(top_margin + y_ratio * graph_h)
            
            # Grid Line
            painter.setPen(QColor(100, 100, 100, 50))
            painter.drawLine(left_margin, y, w - right_margin, y)
            
            # Label
            value = int(self.max_value * (1.0 - y_ratio))
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(0, y + 4, 30, 20, Qt.AlignmentFlag.AlignRight, f"{value}")
            
        # Draw Charts
        for i, history in enumerate(self.data_history):
            if len(history) < 2: continue
            
            path = QPainterPath()
            step_x = graph_w / (self.history_size - 1)
            
            # Map value 0..max to h..0 (inverted y) within graph area
            def val_to_y(v):
                ratio = min(v / self.max_value, 1.0)
                return top_margin + graph_h - (ratio * graph_h)

            path.moveTo(w - right_margin - ((len(history)-1) * step_x), val_to_y(history[0]))
            
            for j, val in enumerate(history[1:]):
                x = w - right_margin - ((len(history) - 1 - (j+1)) * step_x)
                y = val_to_y(val)
                path.lineTo(x, y)
                
            painter.setPen(QPen(self.colors[i], 2))
            painter.drawPath(path)

class DashboardTab(QWidget):
    def __init__(self, controller: LegionController):
        super().__init__()
        self.controller = controller
        self.init_ui()
        self.controller.view_dashboard = self

    def init_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setSpacing(20)
        self.setLayout(self.layout)

        # 1. Top Cards (Grid of 4)
        self.cards_layout = QGridLayout()
        self.cpu_card = self.create_card("Temp. CPU")
        self.gpu_card = self.create_card("Temp. GPU")
        self.fan1_card = self.create_card("Vent. 1 RPM")
        self.fan2_card = self.create_card("Vent. 2 RPM")
        
        self.cards_layout.addWidget(self.cpu_card, 0, 0)
        self.cards_layout.addWidget(self.gpu_card, 0, 1)
        self.cards_layout.addWidget(self.fan1_card, 1, 0)
        self.cards_layout.addWidget(self.fan2_card, 1, 1)
        
        self.layout.addLayout(self.cards_layout)

        # 2. Charts (Side by Side)
        self.charts_layout = QHBoxLayout()
        
        self.temp_graph = RealtimeGraph("Historial de Temperatura", ["CPU", "GPU"], [QColor("#007BFF"), QColor("#FF4136")], max_value=100, unit="°C")
        self.fan_graph = RealtimeGraph("Historial de Ventiladores", ["Vent. 1", "Vent. 2"], [QColor("#00D1FF"), QColor("#E54297")], max_value=4500, unit="RPM")
        
        self.charts_layout.addWidget(self.temp_graph)
        self.charts_layout.addWidget(self.fan_graph)
        self.layout.addLayout(self.charts_layout, 1) # Give charts stretch priority

        # 3. System Usage (Progress Bars)
        self.usage_group = QGroupBox("Uso del Sistema")
        self.usage_layout = QVBoxLayout()
        
        self.cpu_usage_bar = self.create_progress_bar("Uso CPU")
        self.ram_usage_bar = self.create_progress_bar("Uso RAM")
        self.gpu_usage_bar = self.create_progress_bar("Uso GPU")
        
        self.usage_layout.addWidget(self.cpu_usage_bar['container'])
        self.usage_layout.addWidget(self.ram_usage_bar['container'])
        self.usage_layout.addWidget(self.gpu_usage_bar['container'])
        
        self.usage_group.setLayout(self.usage_layout)
        self.layout.addWidget(self.usage_group)

    def create_card(self, title):
        frame = QGroupBox() # styled as card
        layout = QVBoxLayout()
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #888; font-size: 12px; font-weight: bold;")
        lbl_value = QLabel("--")
        lbl_value.setStyleSheet("color: #fff; font-size: 24px; font-weight: bold;")
        lbl_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_value)
        frame.setLayout(layout)
        frame.lbl_value = lbl_value # store ref
        return frame

    def create_progress_bar(self, title):
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        
        lbl = QLabel(title)
        lbl.setFixedWidth(100)
        
        # Use our new animated class
        pbar = AnimatedProgressBar()
        pbar.setRange(0, 100)
        pbar.setTextVisible(True)
        pbar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 5px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #00D1FF;
                border-radius: 4px;
            }
        """)

        lbl_extra = QLabel("") # For e.g. "12GB / 16GB"
        lbl_extra.setFixedWidth(100)
        lbl_extra.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout.addWidget(lbl)
        layout.addWidget(pbar)
        layout.addWidget(lbl_extra)
        container.setLayout(layout)
        
        return {'container': container, 'bar': pbar, 'extra': lbl_extra}

    def set_mode(self, mode_name):
        log.info("Dashboard loading preset: %s", mode_name)
        # Only load the software preset to avoid requiring sudo for hardware changes
        self.controller.on_load_from_preset(mode_name)

    @pyqtSlot(object, object, object, object, str, object, object, object)
    def update_stats(self, cpu_temp, gpu_temp, fan1_rpm, fan2_rpm, profile, cpu_usage, ram_usage, gpu_usage):
        # Update Cards
        self.cpu_card.lbl_value.setText(f"{cpu_temp}°C")
        self.gpu_card.lbl_value.setText(f"{gpu_temp}°C")
        self.fan1_card.lbl_value.setText(f"{fan1_rpm}")
        self.fan2_card.lbl_value.setText(f"{fan2_rpm}")

        # Update Graphs
        self.temp_graph.add_data([cpu_temp, gpu_temp])
        self.fan_graph.add_data([fan1_rpm, fan2_rpm])

        # Update Progress Bars
        self.cpu_usage_bar['bar'].setValueSmooth(int(cpu_usage))
        
        self.ram_usage_bar['bar'].setValueSmooth(int(ram_usage[0]))
        self.ram_usage_bar['extra'].setText(f"{ram_usage[1]}GB / {ram_usage[2]}GB")
        
        self.gpu_usage_bar['bar'].setValueSmooth(int(gpu_usage[0]))
        if gpu_usage[1] > 0:
             self.gpu_usage_bar['extra'].setText(f"{int(gpu_usage[1])} MB")
        
        # Also update FanCurve tab if visible - REMOVING this potential crash point
        # if self.controller.view_fancurve:
        #     pass

# Automation and Log tabs removed for simplification

# pylint: disable=too-few-public-methods


# pylint: disable=too-few-public-methods
class Tabs(QTabWidget):
    def __init__(self, controller):
        print("DEBUG: Tabs.__init__ started")
        super().__init__()
        # setup controller
        self.controller = controller
        self.controller.tabs = self

        # setup tabs
        print("DEBUG: Creating tab views")
        self.tabs = [
            ("Panel", DashboardTab(controller)),
            ("Curva de Ventiladores", FanCurveTab(controller)),
            ("Otras Opciones", OtherOptionsTab(controller))
        ]

        for tab_name, tab in self.tabs:
            area = QScrollArea()
            area.setWidget(tab)
            area.setWidgetResizable(True)
            self.addTab(area, tab_name)




# pylint: disable=too-few-public-methods


class MainWindow(QMainWindow):
    controller:LegionController

    def __init__(self, controller:LegionController, icon:QtGui.QIcon):
        super().__init__()
        # setup controller
        self.controller = controller
        self.controller.main_window = self

        # Set a minium width to the window
        self.setMinimumSize(1250, 725)

        # window layout
        self.setWindowTitle("LenovoLegionLinux")
        self.icon = icon
        self.setWindowIcon(self.icon)
        
        print("DEBUG: MainWindow calling init_ui")
        self.init_ui(controller)
        print("DEBUG: MainWindow.__init__ finished")



    
    def init_ui(self, controller):
        print("DEBUG: MainWindow.init_ui started")
        # tabs
        self.tabs = Tabs(controller)

        # bottom buttons
        self.quit_button = QPushButton("Salir")
        self.quit_button.clicked.connect(controller.app_close)
        self.ok_button = QPushButton("Guardar")
        self.ok_button.clicked.connect(controller.save_settings)
        self.ok_quit_button = QPushButton("Guardar y Salir")
        self.ok_quit_button.clicked.connect(controller.app_close_and_save)
        self.button_layout = QHBoxLayout()
        # Center with stretches on both sides
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.quit_button)
        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.ok_quit_button)
        self.button_layout.addStretch()

        # main layout
        self.main_layout = QVBoxLayout()

        self.main_layout.addWidget(self.tabs, 1)
        self.main_layout.addLayout(self.button_layout)

        # use main layout for main window
        self.main_widget = QWidget()
        self.main_widget.setLayout(self.main_layout)

        # set main widget
        self.setCentralWidget(self.main_widget)

        # display of root warning message
        self.show_root_dialog = False
        self.onstart_timer = QtCore.QTimer()
        self.onstart_timer.singleShot(0, self.on_start)

        # timer to automatically close window during testing in CI
        self.close_timer = QTimer()



    def on_start(self):
        if self.show_root_dialog:
            QMessageBox.critical(
                self, "Error", "The program must be run as root!")

        if self.controller.model.app_model.open_closed_to_tray.get():
            self.hide_to_tray()

    # pylint: disable=invalid-name
    def closeEvent(self, event):
        # Overide the close event of pyqt
        log.info("Received close event")
        if self.controller.model.app_model.close_to_tray.get():
            log.info("Ignore close event and hide to tray instead.")
            event.ignore()
            self.hide_to_tray()
        else:
            log.info("Accept close event and close.")
            self.controller.app_close()
            event.accept()

    def close_after(self, milliseconds: int):
        self.close_timer.timeout.connect(self.close)
        self.close_timer.start(milliseconds)

    def bring_to_foreground(self):
        self.setWindowFlag(QtCore.Qt.WindowType.Window)
        self.setWindowFlags(self.windowFlags() & (~QtCore.Qt.WindowType.Tool))
        self.setWindowState(self.windowState(
        ) & ~QtCore.Qt.WindowState.WindowMinimized | QtCore.Qt.WindowState.WindowActive)
        self.activateWindow()
        self.show()

    def hide_to_tray(self):
        if not self.controller.model.is_root_user():
            # do not hide to tray when running as root because
            # a program run as root cannot usually
            # show a tray icon
            self.setWindowFlag(QtCore.Qt.WindowType.Tool)
            self.hide()


class LegionTray:
    def __init__(self, icon, main_window:QMainWindow, controller:LegionController):
        self.tray = QSystemTrayIcon(icon, main_window)
        self.tray.setIcon(icon)
        self.tray.setVisible(True)
        self.controller = controller

        self.menu = QMenu()
        def add_action(text):
            act = QAction(text)
            self.menu.addAction(act)
            return act

        # title
        self.title = QAction("Legion")
        self.title.setEnabled(False)
        self.menu.addAction(self.title)
        # ---
        self.menu.addSeparator()
        # open
        self.open_action = QAction("Mostrar")
        self.open_action.triggered.connect(self.controller.app_show)
        self.menu.addAction(self.open_action)
        # quit
        self.quit_action = QAction("Salir")
        self.quit_action.triggered.connect(self.controller.app_close)
        self.menu.addAction(self.quit_action)
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        # ---
        self.menu.addSeparator()
        self.batteryconservation_action = QAction("Modo Conservación")
        self.menu.addAction(self.batteryconservation_action)
        self.rapid_charging_action = QAction("Carga Rápida")
        self.menu.addAction(self.rapid_charging_action)
        self.fnlock_action = QAction("Bloqueo Fn")
        self.menu.addAction(self.fnlock_action)
        print("DEBUG: LegionTray.__init__ finished")
        self.touchpad_action = QAction("Touchpad Habilitado")
        self.menu.addAction(self.touchpad_action)
        self.always_on_usb_charging_action = QAction("Carga USB Siempre Activa")
        self.menu.addAction(self.always_on_usb_charging_action)
        # ---
        self.menu.addSeparator()
        self.preset1_action = add_action("preset")
        self.preset2_action = add_action("preset")
        self.preset3_action = add_action("preset")
        self.preset4_action = add_action("preset")
        self.preset5_action = add_action("preset")
        self.preset6_action = add_action("preset")
        self.preset7_action = add_action("preset")
        self.preset8_action = add_action("preset")
        # ---
        self.menu.addSeparator()
        self.powermode1_action = add_action("powermode")
        self.powermode2_action = add_action("powermode")
        self.powermode3_action = add_action("powermode")
        self.powermode4_action = add_action("powermode")


    def show_message(self, title):
        self.tray.setToolTip(title)
        self.tray.showMessage(title, title)

    def show(self):
        self.tray.show()


def get_ressource_path(name):
    path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), name)
    return path

# Disable linter error since this is simplier than refactored into lookup table
# with less branches
# pylint: disable=too-many-branches
def get_icon_path(controller):
    icon_color = 'color'
    if controller.model.app_model.icon_color_mode.get() == 'always-color':
        icon_color = 'color'
    elif controller.model.app_model.icon_color_mode.get() == 'always-light':
        icon_color = 'light'
    elif controller.model.app_model.icon_color_mode.get() == 'always-dark':
        icon_color = 'dark'
    elif controller.model.app_model.icon_color_mode.get() == 'automatic':
        color_mode = get_color_mode()
        log.info("Using color mode: %s", color_mode)
        if color_mode == 'dark':
            icon_color = 'dark'
        elif color_mode == 'light':
            icon_color = 'light'
        else:
            icon_color = 'color'
    elif controller.model.app_model.icon_color_mode.get() == 'automatic-inverted':
        color_mode = get_color_mode()
        log.info("Using color mode: %s", color_mode)
        if color_mode == 'dark':
            icon_color = 'light'
        elif color_mode == 'light':
            icon_color = 'dark'
        else:
            icon_color = 'color'

    log.info("Using icon_color %s", icon_color)
    if icon_color == 'dark':
        log.info("Using icon legion_logo_dark")
        icon_path = get_ressource_path('legion_logo_dark.png')
    elif icon_color == 'light':
        log.info("Using icon legion_logo_light")
        icon_path = get_ressource_path('legion_logo_light.png')
    else:
        log.info("Using icon legion_logo")
        icon_path = get_ressource_path('legion_logo.png')
    return icon_path

def get_stylesheet(theme_mode='dark'):
    is_dark = theme_mode == 'dark'
    
    # Base Colors
    bg_color = "#0E110E" if is_dark else "#F5F7F8"
    fg_color = "#FFFFFF" if is_dark else "#2D3436"
    panel_bg = "#202C41" if is_dark else "#FFFFFF"
    border_color = "#343F52" if is_dark else "#D1D8E0"
    tab_bg = "#202C41" if is_dark else "#E8ECEF"
    accent_blue = "#43D2DE" if is_dark else "#007BFF"
    accent_pink = "#E54297" if is_dark else "#D63384"
    
    return f"""
        QWidget {{
            background-color: {bg_color};
            color: {fg_color};
            font-family: 'Segoe UI', 'Roboto', sans-serif;
            font-size: 13px;
        }}
        QMainWindow, QDialog, QTabWidget::pane {{
            border: 1px solid {border_color};
        }}
        QGroupBox {{
            border: 2px solid {border_color};
            border-radius: 8px;
            margin-top: 15px;
            font-weight: bold;
            color: {fg_color};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }}
        QPushButton {{
            background-color: {panel_bg};
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 6px 12px;
            color: {fg_color};
        }}
        QPushButton:hover {{
            background-color: {"#343F52" if is_dark else "#E9ECEF"};
            border: 1px solid {accent_blue};
        }}
        
        /* Dashboard Mode Buttons - Neon Neon Neon! */
        /* Dashboard Mode Buttons - Solid & Vibrant */
        QPushButton#quiet_btn {{
            background-color: #00D1FF;
            color: white;
            border: none;
            font-weight: bold;
            font-size: 16px;
            padding: 10px;
            border-radius: 8px;
        }}
        QPushButton#quiet_btn:hover {{
            background-color: #00B6E0;
        }}
        
        QPushButton#balanced_btn {{
            background-color: #FFFFFF;
            color: #000000;
            border: 1px solid #D1D8E0;
            font-weight: bold;
            font-size: 16px;
            padding: 10px;
            border-radius: 8px;
        }}
        QPushButton#balanced_btn:hover {{
            background-color: #F0F0F0;
        }}
        
        QPushButton#perf_btn {{
            background-color: #FF3131;
            color: white;
            border: none;
            font-weight: bold;
            font-size: 16px;
            padding: 10px;
            border-radius: 8px;
        }}
        QPushButton#perf_btn:hover {{
            background-color: #E62020;
        }}

        QLineEdit, QSpinBox, QComboBox {{
            background-color: {bg_color};
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 4px;
            color: {fg_color};
        }}
        
        QComboBox QLineEdit {{
            background: transparent;
            padding: 0px;
            margin: 0px;
        }}
        
        QComboBox::drop-down {{
            border: none;
            width: 0px;
        }}
        QComboBox::down-arrow {{
            image: none;
            width: 0px;
        }}
        
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 0px;
            border: none;
        }}
        QSpinBox::up-arrow, QSpinBox::down-arrow {{
            image: none;
        }}

        QTabBar::tab {{
            background: {tab_bg};
            border: 1px solid {border_color};
            padding: 8px 15px;
        }}
        QTabBar::tab:selected {{
            background: {accent_blue};
            color: {"#0E110E" if is_dark else "white"};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            background-color: {panel_bg};
            border: 1px solid {border_color};
            border-radius: 3px;
        }}
        QCheckBox::indicator:checked {{
            background-color: {accent_pink};
        }}
        QScrollArea {{
            border: none;
            background-color: {bg_color};
        }}
    """

def main():
    # Set the desktop file name
    # This make the window icon appear on wayland
    QGuiApplication.setDesktopFileName("legion_gui.desktop")

    app = QApplication(sys.argv)
    
    # Apply a temporary default theme; the saved preference will be applied after loading settings
    theme = get_color_mode()
    if theme == 'unknown': theme = 'dark'
    app.setStyleSheet(get_stylesheet(theme))

    use_legion_cli_to_write = '--use_legion_cli_to_write' in sys.argv
    # When running as a regular user, writing to sysfs will fail and can cause the GUI
    # to exit unexpectedly depending on the code path. Default to using the CLI via
    # pkexec/polkit for privileged writes.
    if (not use_legion_cli_to_write) and (os.geteuid() != 0):
        use_legion_cli_to_write = True
    # Determine config directory
    if os.geteuid() == 0:
        config_dir = "/etc/legion_linux"
    else:
        config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        config_dir = os.path.join(config_home, 'legion_linux')
    
    # Ensure config directory exists
    try:
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            print(f"Created config directory: {config_dir}")
    except Exception as e:
        print(f"Error creating config directory {config_dir}: {e}")

    do_not_excpect_hwmon = False
    controller = LegionController(app, expect_hwmon=not do_not_excpect_hwmon,
                             use_legion_cli_to_write=use_legion_cli_to_write,
                             config_dir=config_dir)

    # Load savable settings from file if exists
    controller.model.load_settings()

    # Overwrite settings from commandline args
    if '--automaticclose' in sys.argv:
        controller.model.app_model.automatic_close.set(True)
    if '--close_to_tray' in sys.argv:
        controller.model.app_model.close_to_tray.set(True)
    if '--open_closed_to_tray' in sys.argv:
        controller.model.app_model.open_closed_to_tray.set(True)

    # Overwrite settings by rules
    if controller.model.is_root_user():
        # When GUI is run as root it usually cannot display
        # a icon in the tray due to security of XServer,
        # so disable opening or closing minimized in tray,
        # otherwise there is no way to close the program
        # except sending a kill signal
        #
        # https://forum.qt.io/topic/78464/system-tray-icon-missing-when-running-as-root/5
        controller.model.app_model.open_closed_to_tray.set(False)
        controller.model.app_model.close_to_tray.set(False)

    # Resources
    icon_path = get_icon_path(controller)
    icon = QtGui.QIcon(icon_path)
    # Set tray icon to the window icon
    # Can't be use since tray icon is a svg
    # Only support png and ico
    # (maybe if PyQT6 introduce svg support)
    #QGuiApplication.setWindowIcon(icon)

    # Main Windows
    main_window = MainWindow(controller, icon)
    controller.init(read_from_hw=not do_not_excpect_hwmon)

    # Apply persisted theme preference (overrides the initial autodetect)
    controller.init_theme_from_settings()

    # Tray
    # tray = LegionTray(icon, main_window, controller)
    # tray.show()
    # controller.tray = tray
    controller.tray = None
    controller.init_tray()

    # Start Windows
    if controller.model.app_model.automatic_close.get():
        main_window.close_after(3000)
    main_window.show()

    # Run
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
