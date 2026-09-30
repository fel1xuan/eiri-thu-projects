import math

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class PandasTableModel(QAbstractTableModel):
    """Read-only Qt model for displaying a pandas DataFrame."""

    def __init__(self, dataframe=None, parent=None):
        super().__init__(parent)
        self._dataframe = dataframe.copy() if dataframe is not None else pd.DataFrame()

    def set_dataframe(self, dataframe):
        self.beginResetModel()
        self._dataframe = dataframe.copy() if dataframe is not None else pd.DataFrame()
        self.endResetModel()

    @property
    def dataframe(self):
        return self._dataframe

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._dataframe.index)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._dataframe.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        return _format_cell_value(self._dataframe.iat[index.row(), index.column()])

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._dataframe.columns):
            return str(self._dataframe.columns[section])
        if orientation == Qt.Vertical:
            return str(section + 1)
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


def _format_cell_value(value):
    if value is None or value is pd.NaT:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        if value.hour == value.minute == value.second == value.microsecond == 0:
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return str(int(value))
        return f"{value:g}"
    return str(value)
