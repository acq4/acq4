from acq4.util import Qt


class NameEmittingPushButton(Qt.QPushButton):
    clickedWithName = Qt.Signal(str, bool)

    def __init__(self, *args, **kwargs):
        super(NameEmittingPushButton, self).__init__(*args, **kwargs)
        self.clicked.connect(self._emitClickedWithName)

    def _emitClickedWithName(self, checked):
        self.clickedWithName.emit(self.text(), checked)


class NamedNormalizedSlider(Qt.QSlider):
    valueChangedWithName = Qt.Signal(str, int)

    def __init__(self, name, *args, **kwargs):
        super(NamedNormalizedSlider, self).__init__(*args, **kwargs)
        self._name = name
        self.valueChanged.connect(self._handleValueChanged)

    def _handleValueChanged(self, val):
        self.valueChangedWithName.emit(self._name, val / 99.)