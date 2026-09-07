# Explicitly import the submodules or classes you need
from PyQt6 import QtCore, QtWidgets

# Now you can use them normally
print("Qt Version:", QtCore.QT_VERSION_STR)
app = QtWidgets.QApplication([])
