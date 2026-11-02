import sys
import csv
import json
import math
from pathlib import Path

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox,
    QToolBar, QListWidget, QListWidgetItem, QDockWidget, QColorDialog,
    QComboBox, QInputDialog, QVBoxLayout, QLabel
)


def read_data(filename):
    """Read numeric X/Y pairs from .data, CSV or TSV."""
    points = []
    path = Path(filename)

    if path.suffix.lower() in (".csv", ".tsv"):
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        with open(path, "r", encoding="utf-8-sig") as f:
            for row in csv.reader(f, delimiter=delimiter):
                if len(row) < 2:
                    continue
                try:
                    x, y = float(row[0]), float(row[1])
                    if math.isfinite(x) and math.isfinite(y):
                        points.append((x, y))
                except ValueError:
                    continue
    else:
        with open(filename, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(("#", ";", "//)):
                    continue
                line = line.replace(",", ".")
                parts = line.replace(";", " ").replace("\t", " ").split()
                if len(parts) < 2:
                    continue
                try:
                    x, y = float(parts[0]), float(parts[1])
                    if math.isfinite(x) and math.isfinite(y):
                        points.append((x, y))
                except ValueError:
                    continue

    if not points:
        raise ValueError("Не найдено ни одной числовой пары X/Y.")
    return points


class PlotCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.curves = []
        self.log_x = False
        self.log_y = False
        self.setMinimumSize(500, 350)

    def transformed(self, value, logarithmic):
        if logarithmic:
            return math.log10(value) if value > 0 else None
        return value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("white"))

        left, top, right, bottom = 75, 35, self.width() - 30, self.height() - 65
        if right <= left or bottom <= top:
            return

        all_points = []
        for curve in self.curves:
            if not curve["visible"]:
                continue
            for x, y in curve["points"]:
                tx = self.transformed(x, self.log_x)
                ty = self.transformed(y, self.log_y)
                if tx is not None and ty is not None:
                    all_points.append((tx, ty))

        if not all_points:
            painter.setPen(QColor("#555555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Откройте файл с числовыми данными X/Y")
            return

        xmin = min(p[0] for p in all_points)
        xmax = max(p[0] for p in all_points)
        ymin = min(p[1] for p in all_points)
        ymax = max(p[1] for p in all_points)

        if xmin == xmax:
            xmin -= 0.5
            xmax += 0.5
        if ymin == ymax:
            ymin -= 0.5
            ymax += 0.5

        dx, dy = (xmax - xmin) * 0.05, (ymax - ymin) * 0.05
        xmin, xmax = xmin - dx, xmax + dx
        ymin, ymax = ymin - dy, ymax + dy

        def screen(x, y):
            return QPointF(
                left + (x - xmin) / (xmax - xmin) * (right - left),
                bottom - (y - ymin) / (ymax - ymin) * (bottom - top)
            )

        painter.setFont(QFont("Times New Roman", 9))
        painter.setPen(QPen(QColor("#dddddd"), 1))
        for i in range(11):
            xx = left + i * (right - left) / 10
            yy = top + i * (bottom - top) / 10
            painter.drawLine(round(xx), top, round(xx), bottom)
            painter.drawLine(left, round(yy), right, round(yy))

        painter.setPen(QPen(QColor("black"), 1.4))
        painter.drawLine(left, top, left, bottom)
        painter.drawLine(left, bottom, right, bottom)

        for i in range(6):
            xv = xmin + i * (xmax - xmin) / 5
            yv = ymin + i * (ymax - ymin) / 5
            xs = 10 ** xv if self.log_x else xv
            ys = 10 ** yv if self.log_y else yv
            painter.drawText(round(left + i * (right-left)/5 - 25),
                             bottom + 22, f"{xs:.4g}")
            painter.drawText(5, round(bottom - i * (bottom-top)/5 + 4),
                             f"{ys:.4g}")

        painter.drawText((left + right)//2, self.height() - 15, "X")
        painter.save()
        painter.translate(18, (top + bottom)//2)
        painter.rotate(-90)
        painter.drawText(0, 0, "Y")
        painter.restore()

        for curve in self.curves:
            if not curve["visible"]:
                continue
            painter.setPen(QPen(QColor(curve["color"]), curve["width"]))
            previous = None
            for x, y in curve["points"]:
                tx = self.transformed(x, self.log_x)
                ty = self.transformed(y, self.log_y)
                if tx is None or ty is None:
                    previous = None
                    continue
                point = screen(tx, ty)
                if previous is not None:
                    painter.drawLine(previous, point)
                painter.drawEllipse(point, 2.2, 2.2)
                previous = point

        painter.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EngPlot — инженерные графики")
        self.resize(1100, 720)

        self.canvas = PlotCanvas()
        self.setCentralWidget(self.canvas)

        self.list_widget = QListWidget()
        dock = QDockWidget("Кривые", self)
        dock.setWidget(self.list_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.list_widget.itemChanged.connect(self.visibility_changed)
        self.list_widget.currentRowChanged.connect(lambda _: self.canvas.update())

        toolbar = QToolBar("Главная")
        self.addToolBar(toolbar)

        actions = [
            ("Открыть данные", self.open_files),
            ("Цвет кривой", self.change_color),
            ("Переименовать", self.rename_curve),
            ("Удалить", self.delete_curve),
            ("Сохранить проект", self.save_project),
            ("Открыть проект", self.load_project),
            ("Экспорт PNG", self.export_png),
        ]
        for label, function in actions:
            from PySide6.QtGui import QAction
            action = QAction(label, self)
            action.triggered.connect(function)
            toolbar.addAction(action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" X: "))
        self.x_scale = QComboBox()
        self.x_scale.addItems(["Линейная X", "Логарифмическая X"])
        self.x_scale.currentIndexChanged.connect(self.change_scale)
        toolbar.addWidget(self.x_scale)

        toolbar.addWidget(QLabel(" Y: "))
        self.y_scale = QComboBox()
        self.y_scale.addItems(["Линейная Y", "Логарифмическая Y"])
        self.y_scale.currentIndexChanged.connect(self.change_scale)
        toolbar.addWidget(self.y_scale)

        self.statusBar().showMessage("Готово")

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Открыть данные", "",
            "Файлы данных (*.data *.txt *.csv *.tsv);;Все файлы (*.*)"
        )
        for filename in files:
            try:
                points = read_data(filename)
                curve = {
                    "name": Path(filename).stem,
                    "file": filename,
                    "points": points,
                    "visible": True,
                    "color": "#1769aa",
                    "width": 1.5,
                }
                self.canvas.curves.append(curve)
                item = QListWidgetItem(curve["name"])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.list_widget.addItem(item)
                self.statusBar().showMessage(
                    f"{curve['name']}: загружено {len(points)} точек"
                )
            except Exception as exc:
                QMessageBox.warning(self, "Ошибка импорта",
                                    f"{filename}\n\n{exc}")
        self.canvas.update()

    def visibility_changed(self, item):
        index = self.list_widget.row(item)
        if 0 <= index < len(self.canvas.curves):
            self.canvas.curves[index]["visible"] = (
                item.checkState() == Qt.CheckState.Checked
            )
            self.canvas.update()

    def selected_curve(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.canvas.curves):
            return row, self.canvas.curves[row]
        QMessageBox.information(self, "Кривые", "Сначала выберите кривую.")
        return None, None

    def change_color(self):
        row, curve = self.selected_curve()
        if curve is None:
            return
        color = QColorDialog.getColor(QColor(curve["color"]), self)
        if color.isValid():
            curve["color"] = color.name()
            self.canvas.update()

    def rename_curve(self):
        row, curve = self.selected_curve()
        if curve is None:
            return
        name, ok = QInputDialog.getText(
            self, "Имя кривой", "Название:", text=curve["name"]
        )
        if ok and name.strip():
            curve["name"] = name.strip()
            self.list_widget.item(row).setText(curve["name"])

    def delete_curve(self):
        row, curve = self.selected_curve()
        if curve is not None:
            self.canvas.curves.pop(row)
            self.list_widget.takeItem(row)
            self.canvas.update()

    def change_scale(self):
        self.canvas.log_x = self.x_scale.currentIndex() == 1
        self.canvas.log_y = self.y_scale.currentIndex() == 1
        self.canvas.update()

    def save_project(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Сохранить проект", "project.json", "EngPlot (*.json)"
        )
        if not filename:
            return
        data = []
        for curve in self.canvas.curves:
            data.append({
                "name": curve["name"],
                "points": curve["points"],
                "visible": curve["visible"],
                "color": curve["color"],
                "width": curve["width"],
            })
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump({
                    "curves": data,
                    "log_x": self.canvas.log_x,
                    "log_y": self.canvas.log_y,
                }, f, ensure_ascii=False)
            self.statusBar().showMessage("Проект сохранён")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка сохранения", str(exc))

    def load_project(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Открыть проект", "", "EngPlot (*.json)"
        )
        if not filename:
            return
        try:
            with open(filename, encoding="utf-8") as f:
                data = json.load(f)
            self.canvas.curves = data.get("curves", [])
            self.canvas.log_x = data.get("log_x", False)
            self.canvas.log_y = data.get("log_y", False)
            self.list_widget.clear()
            for curve in self.canvas.curves:
                item = QListWidgetItem(curve["name"])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if curve["visible"]
                    else Qt.CheckState.Unchecked
                )
                self.list_widget.addItem(item)
            self.x_scale.setCurrentIndex(1 if self.canvas.log_x else 0)
            self.y_scale.setCurrentIndex(1 if self.canvas.log_y else 0)
            self.canvas.update()
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка проекта", str(exc))

    def export_png(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Экспорт PNG", "plot.png", "PNG (*.png)"
        )
        if not filename:
            return
        pixmap = self.canvas.grab()
        if not pixmap.save(filename, "PNG"):
            QMessageBox.warning(self, "Экспорт", "Не удалось сохранить PNG.")
        else:
            self.statusBar().showMessage(f"Сохранено: {filename}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
