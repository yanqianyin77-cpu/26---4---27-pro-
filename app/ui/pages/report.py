from __future__ import annotations

from collections import Counter

from PySide6.QtCharts import QBarSeries, QBarSet, QChart, QChartView, QPieSeries, QValueAxis, QBarCategoryAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from app.ui.components.card import Card


class ReportPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.build()

    def build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.top_grid = QGridLayout()
        self.top_grid.setHorizontalSpacing(14)
        self.top_grid.setVerticalSpacing(14)
        layout.addLayout(self.top_grid)
        self.summary_card = Card(parent=self)
        layout.addWidget(self.summary_card)
        chart_grid = QGridLayout()
        chart_grid.setHorizontalSpacing(14)
        layout.addLayout(chart_grid)
        self.trend_card = Card(parent=self)
        self.dist_card = Card(parent=self)
        chart_grid.addWidget(self.trend_card, 0, 0)
        chart_grid.addWidget(self.dist_card, 0, 1)
        self.refresh()

    def refresh(self):
        while self.top_grid.count():
            item = self.top_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = self.main_window.store.list_vocab()
        mistakes = self.main_window.store.list_mistakes()
        tests = self.main_window.store.list_test_records(20)
        stats = [
            ("词汇总数", len(rows)),
            ("已掌握", sum(1 for row in rows if row.get("mastered"))),
            ("学习中", sum(1 for row in rows if not row.get("mastered"))),
            ("错题数", len(mistakes)),
        ]
        for idx, (label, value) in enumerate(stats):
            card = Card(parent=self)
            card.layout.addWidget(QLabel(label))
            text = QLabel(str(value))
            text.setStyleSheet("font: 700 28px 'Microsoft YaHei UI';")
            card.layout.addWidget(text)
            self.top_grid.addWidget(card, 0, idx)

        self.summary_card.layout.addWidget(QLabel("薄弱点分析"))
        for idx in reversed(range(1, self.summary_card.layout.count())):
            widget = self.summary_card.layout.itemAt(idx).widget()
            if widget:
                widget.deleteLater()
        weak_lines = self.main_window.weak_point_analysis()
        for line in weak_lines:
            label = QLabel(line)
            label.setWordWrap(True)
            self.summary_card.layout.addWidget(label)

        self._draw_trend(tests)
        self._draw_distribution(rows)

    def _clear_layout(self, card):
        for idx in reversed(range(card.layout.count())):
            widget = card.layout.itemAt(idx).widget()
            if widget:
                widget.deleteLater()

    def _draw_trend(self, records):
        self._clear_layout(self.trend_card)
        self.trend_card.layout.addWidget(QLabel("复习趋势图"))
        chart = QChart()
        chart.legend().hide()
        set0 = QBarSet("正确率")
        categories = []
        for idx, row in enumerate(records[-12:]):
            set0.append(row["accuracy"])
            categories.append(str(idx + 1))
        if not categories:
            self.trend_card.layout.addWidget(QLabel("还没有足够的记录。"))
            return
        series = QBarSeries()
        series.append(set0)
        chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        chart.setBackgroundVisible(False)
        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        self.trend_card.layout.addWidget(chart_view)

    def _draw_distribution(self, rows):
        self._clear_layout(self.dist_card)
        self.dist_card.layout.addWidget(QLabel("词性掌握分布"))
        counter = Counter((row.get("pos") or "未分类") for row in rows)
        if not counter:
            self.dist_card.layout.addWidget(QLabel("还没有足够的词汇数据。"))
            return
        pie = QPieSeries()
        for label, count in counter.most_common(6):
            pie.append(label, count)
        chart = QChart()
        chart.addSeries(pie)
        chart.setBackgroundVisible(False)
        chart.legend().setAlignment(Qt.AlignBottom)
        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        self.dist_card.layout.addWidget(chart_view)
