from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()

# The app dashboard imports only QtQuick and QtQuick.Layouts. Shipping every
# Qt QML plugin also pulls in optional WebEngine, 3D, multimedia, and chart DLLs.
allowed_qml_roots = ("PySide6/qml/QtCore", "PySide6/qml/QtQml", "PySide6/qml/QtQuick")

def required_qml_file(item):
    destination = item[1].replace(chr(92), "/")
    return any(destination == root or destination.startswith(root + "/") for root in allowed_qml_roots)

binaries += [item for item in qml_binaries if required_qml_file(item)]
datas += [item for item in qml_datas if required_qml_file(item)]
