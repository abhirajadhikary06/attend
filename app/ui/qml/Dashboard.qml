import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    color: Theme.bg
    clip: true
    opacity: 0
    Component.onCompleted: opacity = 1
    Behavior on opacity { NumberAnimation { duration: 420; easing.type: Easing.OutCubic } }

    // ------------------------------------------------------------------ components
    component PillButton: Rectangle {
        id: pb
        property string text: ""
        property bool primary: false
        property string iconName: ""
        signal clicked()
        implicitWidth: pbRow.implicitWidth + 40
        implicitHeight: 46
        radius: height / 2
        color: primary ? (pbMouse.containsMouse ? "#e4e4e7" : Theme.text)
                       : (pbMouse.containsMouse ? Theme.hover : Theme.elevated)
        border.width: primary ? 0 : 1
        border.color: pbMouse.containsMouse ? Theme.borderStrong : Theme.border
        scale: pbMouse.pressed ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }
        Behavior on color { ColorAnimation { duration: 140 } }
        Row {
            id: pbRow
            anchors.centerIn: parent
            spacing: 8
            Image {
                visible: pb.iconName !== ""
                width: 18; height: 18
                anchors.verticalCenter: parent.verticalCenter
                sourceSize: Qt.size(36, 36)
                source: pb.iconName !== "" ? "image://icons/" + pb.iconName + "/" + (pb.primary ? "09090b" : "fafafa") : ""
            }
            Text {
                text: pb.text
                color: pb.primary ? Theme.bg : Theme.text
                font.pixelSize: 14
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        MouseArea {
            id: pbMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: pb.clicked()
        }
    }

    component Panel: Rectangle {
        id: pn
        property string title: ""
        property string subtitle: ""
        default property alias content: inner.data
        radius: 14
        color: Theme.surface
        border.width: 1
        border.color: Theme.border
        implicitHeight: inner.implicitHeight + 40
        ColumnLayout {
            id: inner
            x: 20; y: 20
            width: pn.width - 40
            spacing: 12
            RowLayout {
                visible: pn.title !== ""
                Layout.fillWidth: true
                Text {
                    text: pn.title
                    color: Theme.text
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: pn.subtitle
                    color: Theme.muted
                    font.pixelSize: 12
                }
            }
        }
    }

    component StatCard: Rectangle {
        id: sc
        property string label: ""
        property int target: 0
        property int shown: target
        property string textValue: ""
        property string hint: ""
        property string iconName: ""
        Behavior on shown { NumberAnimation { duration: 800; easing.type: Easing.OutCubic } }
        implicitHeight: 120
        radius: 14
        color: Theme.surface
        border.width: 1
        border.color: Theme.border
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 2
            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: sc.label
                    color: Theme.textDim
                    font.pixelSize: 13
                    Layout.fillWidth: true
                }
                Image {
                    width: 18; height: 18
                    sourceSize: Qt.size(36, 36)
                    source: "image://icons/" + sc.iconName + "/71717a"
                }
            }
            Item { Layout.fillHeight: true }
            Text {
                text: sc.textValue !== "" ? sc.textValue : sc.shown
                color: Theme.text
                font.pixelSize: sc.textValue !== "" ? 20 : 34
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Text {
                text: sc.hint
                color: Theme.muted
                font.pixelSize: 12
            }
        }
    }

    component ActionTile: Rectangle {
        id: at
        property string title: ""
        property string desc: ""
        property string iconName: ""
        signal clicked()
        implicitHeight: 138
        radius: 14
        color: atMouse.containsMouse ? Theme.elevated : Theme.surface
        border.width: 1
        border.color: atMouse.containsMouse ? Theme.accent : Theme.border
        Behavior on color { ColorAnimation { duration: 140 } }
        Behavior on border.color { ColorAnimation { duration: 140 } }
        transform: Translate {
            y: atMouse.containsMouse ? -3 : 0
            Behavior on y { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        }
        Rectangle {
            x: 18; y: 18
            width: 40; height: 40
            radius: 12
            color: Theme.accentSoft
            Image {
                anchors.centerIn: parent
                width: 20; height: 20
                sourceSize: Qt.size(40, 40)
                source: "image://icons/" + at.iconName + "/818cf8"
            }
        }
        Image {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 18
            width: 16; height: 16
            sourceSize: Qt.size(32, 32)
            opacity: atMouse.containsMouse ? 1 : 0.4
            Behavior on opacity { NumberAnimation { duration: 140 } }
            source: "image://icons/arrow-up-right/a1a1aa"
        }
        Column {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 18
            spacing: 3
            Text { text: at.title; color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold }
            Text { text: at.desc; color: Theme.muted; font.pixelSize: 12; width: parent.width; wrapMode: Text.WordWrap }
        }
        MouseArea {
            id: atMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: at.clicked()
        }
    }

    component StatusRow: RowLayout {
        id: sr
        property string label: ""
        property string value: ""
        property bool ok: true
        property bool warn: false
        Layout.fillWidth: true
        spacing: 10
        Rectangle {
            width: 8; height: 8; radius: 4
            Layout.alignment: Qt.AlignVCenter
            color: sr.ok ? Theme.green : (sr.warn ? Theme.amber : Theme.red)
        }
        Text { text: sr.label; color: Theme.textDim; font.pixelSize: 13; Layout.fillWidth: true }
        Text { text: sr.value; color: Theme.text; font.pixelSize: 13 }
    }

    // ------------------------------------------------------------------ ambient wash
    Rectangle {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 340
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(0.39, 0.40, 0.95, 0.13) }
            GradientStop { position: 1.0; color: Qt.rgba(0.39, 0.40, 0.95, 0.0) }
        }
    }

    // ------------------------------------------------------------------ content
    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: page.implicitHeight + 64
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        ColumnLayout {
            id: page
            x: 36; y: 30
            width: flick.width - 72
            spacing: 24

            // ---- hero
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 270

                ColumnLayout {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(parent.width * (heroCards.visible ? 0.58 : 1.0), 640)
                    spacing: 16

                    Rectangle {
                        implicitWidth: chipRow.implicitWidth + 24
                        implicitHeight: 28
                        radius: 14
                        color: Theme.elevated
                        border.width: 1
                        border.color: Theme.border
                        Row {
                            id: chipRow
                            anchors.centerIn: parent
                            spacing: 8
                            Rectangle {
                                width: 7; height: 7; radius: 3.5
                                anchors.verticalCenter: parent.verticalCenter
                                color: backend.modelsReady ? Theme.green : Theme.amber
                            }
                            Text {
                                text: backend.modelsReady ? "Recognition running on this device" : "Loading recognition models"
                                color: Theme.textDim
                                font.pixelSize: 12
                            }
                        }
                    }

                    Text {
                        text: "Attendance, recognized\nin real time."
                        color: Theme.text
                        font.pixelSize: 46
                        font.weight: Font.Medium
                        font.letterSpacing: -1.4
                        lineHeight: 0.98
                    }

                    Text {
                        text: backend.greeting + ". " + backend.dateLabel + ". Faces are matched locally and nothing leaves this machine."
                        color: Theme.textDim
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Row {
                        spacing: 10
                        PillButton {
                            text: "Launch Live Scanner"
                            primary: true
                            iconName: "scan-face"
                            onClicked: backend.navigate("live")
                        }
                        PillButton {
                            text: "Enroll New Record"
                            iconName: "user-plus"
                            onClicked: backend.navigate("enroll")
                        }
                    }
                }

                // floating cards, the single decorative moment on this page
                Item {
                    id: heroCards
                    visible: parent.width > 900
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: 380; height: 250

                    Rectangle {
                        id: cardBack
                        property real bob: 0
                        x: 20; y: 100 + bob
                        width: 250; height: 118
                        radius: 16
                        rotation: -4
                        color: Theme.elevated
                        border.width: 1
                        border.color: Theme.borderStrong
                        SequentialAnimation on bob {
                            loops: Animation.Infinite
                            NumberAnimation { from: 0; to: 7; duration: 2600; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 7; to: 0; duration: 2600; easing.type: Easing.InOutSine }
                        }
                        Column {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 6
                            Text { text: "Active session"; color: Theme.muted; font.pixelSize: 12 }
                            Text {
                                text: backend.sessionLabel
                                color: Theme.text
                                font.pixelSize: 17
                                font.weight: Font.DemiBold
                                width: parent.width
                                elide: Text.ElideRight
                            }
                            Row {
                                spacing: 6
                                Rectangle {
                                    width: 7; height: 7; radius: 3.5
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: backend.sessionActive ? Theme.green : Theme.red
                                }
                                Text {
                                    text: backend.sessionActive ? "Accepting marks" : "Scanner will not record"
                                    color: Theme.textDim
                                    font.pixelSize: 12
                                }
                            }
                        }
                    }

                    Rectangle {
                        id: cardFront
                        property real bob: 0
                        x: 120; y: 20 + bob
                        width: 240; height: 132
                        radius: 16
                        rotation: 3
                        color: Theme.surface
                        border.width: 1
                        border.color: Theme.accent
                        SequentialAnimation on bob {
                            loops: Animation.Infinite
                            NumberAnimation { from: 6; to: 0; duration: 3100; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 0; to: 6; duration: 3100; easing.type: Easing.InOutSine }
                        }
                        Column {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 4
                            Text { text: "Present today"; color: Theme.muted; font.pixelSize: 12 }
                            Text {
                                text: backend.todayCount
                                color: Theme.text
                                font.pixelSize: 40
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: "of " + backend.studentCount + " enrolled"
                                color: Theme.textDim
                                font.pixelSize: 12
                            }
                        }
                    }
                }
            }

            // ---- stats
            GridLayout {
                Layout.fillWidth: true
                columns: flick.width > 980 ? 4 : 2
                columnSpacing: 14
                rowSpacing: 14

                StatCard {
                    Layout.fillWidth: true
                    label: "Enrolled students"
                    target: backend.studentCount
                    hint: "Records in the database"
                    iconName: "users"
                }
                StatCard {
                    Layout.fillWidth: true
                    label: "Present today"
                    target: backend.todayCount
                    hint: "Across all sessions"
                    iconName: "calendar"
                }
                StatCard {
                    Layout.fillWidth: true
                    label: "Unknown faces"
                    target: backend.unknownCount
                    hint: "Waiting for review"
                    iconName: "user-x"
                }
                StatCard {
                    Layout.fillWidth: true
                    label: "Session"
                    textValue: backend.sessionLabel
                    hint: backend.sessionActive ? "Active now" : "Outside session hours"
                    iconName: "activity"
                }
            }

            // ---- quick actions
            Text {
                text: "Quick actions"
                color: Theme.text
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
            GridLayout {
                Layout.fillWidth: true
                columns: flick.width > 980 ? 4 : 2
                columnSpacing: 14
                rowSpacing: 14

                ActionTile {
                    Layout.fillWidth: true
                    title: "Live Scanner"
                    desc: "Start recognizing faces from the camera"
                    iconName: "scan-face"
                    onClicked: backend.navigate("live")
                }
                ActionTile {
                    Layout.fillWidth: true
                    title: "Enroll record"
                    desc: "Add a student from a photo or a folder"
                    iconName: "user-plus"
                    onClicked: backend.navigate("enroll")
                }
                ActionTile {
                    Layout.fillWidth: true
                    title: "Attendance register"
                    desc: "Browse sessions by day and review who attended"
                    iconName: "calendar"
                    onClicked: backend.navigate("register")
                }
                ActionTile {
                    Layout.fillWidth: true
                    title: "Manual mark"
                    desc: "Record attendance by student ID with a reason"
                    iconName: "clipboard-check"
                    onClicked: backend.navigate("manual")
                }
            }

            // ---- trend + health + activity
            GridLayout {
                Layout.fillWidth: true
                columns: flick.width > 980 ? 2 : 1
                columnSpacing: 14
                rowSpacing: 14

                Panel {
                    id: trendPanel
                    Layout.fillWidth: true
                    Layout.preferredWidth: 3
                    Layout.alignment: Qt.AlignTop
                    title: "Attendance, last 7 days"
                    subtitle: "Marks per day"

                    property int maxV: {
                        var m = 1
                        for (var i = 0; i < backend.trendValues.length; i++)
                            m = Math.max(m, backend.trendValues[i])
                        return m
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 190
                        spacing: 10
                        Repeater {
                            model: backend.trendValues.length
                            delegate: ColumnLayout {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: 8
                                Item {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Rectangle {
                                        id: bar
                                        anchors.bottom: parent.bottom
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        width: Math.min(40, parent.width)
                                        height: Math.max(4, (parent.height - 24) * (backend.trendValues[index] / trendPanel.maxV))
                                        radius: 8
                                        color: index === backend.trendValues.length - 1 ? Theme.accent : Theme.borderStrong
                                        Behavior on height { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                                    }
                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        anchors.bottom: bar.top
                                        anchors.bottomMargin: 6
                                        text: backend.trendValues[index]
                                        color: Theme.textDim
                                        font.pixelSize: 12
                                    }
                                }
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: backend.trendLabels[index]
                                    color: Theme.muted
                                    font.pixelSize: 12
                                }
                            }
                        }
                    }
                }

                Panel {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 2
                    Layout.alignment: Qt.AlignTop
                    title: "System health"

                    StatusRow {
                        label: "Camera"
                        value: backend.cameraLabel
                        ok: backend.cameraOnline
                    }
                    StatusRow {
                        label: "Recognition models"
                        value: backend.modelsReady ? "Loaded" : "Loading"
                        ok: backend.modelsReady
                        warn: !backend.modelsReady
                    }
                    StatusRow {
                        label: "Database"
                        value: backend.dbOk ? backend.studentCount + " records" : "Unreachable"
                        ok: backend.dbOk
                    }
                    StatusRow {
                        label: "Session"
                        value: backend.sessionActive ? "Active" : "Inactive"
                        ok: backend.sessionActive
                        warn: !backend.sessionActive
                    }
                }

                Panel {
                    Layout.fillWidth: true
                    Layout.columnSpan: flick.width > 980 ? 2 : 1
                    title: "Recent activity"
                    subtitle: "This run"

                    Text {
                        visible: backend.activity.length === 0
                        text: "Nothing recorded yet. Open the Live Scanner to start taking attendance."
                        color: Theme.muted
                        font.pixelSize: 13
                    }
                    Repeater {
                        model: backend.activity
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Rectangle {
                                width: 8; height: 8; radius: 4
                                Layout.alignment: Qt.AlignVCenter
                                color: modelData.kind === "success" ? Theme.green
                                     : (modelData.kind === "warn" ? Theme.amber : Theme.accentHover)
                            }
                            Text {
                                text: modelData.title
                                color: Theme.text
                                font.pixelSize: 13
                                font.weight: Font.Medium
                            }
                            Text {
                                text: modelData.detail
                                color: Theme.textDim
                                font.pixelSize: 13
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: modelData.time
                                color: Theme.muted
                                font.pixelSize: 12
                            }
                        }
                    }
                }
            }
        }
    }
}
