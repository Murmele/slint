// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

/// Close a popup from another popup
#[satchel::test]
fn popup_close() {
    slint::slint! {
        export global GlobalProperties {
            in-out property <bool> popup-opened: false;
            in-out property <bool> popup-closed: false;
        }

        export component App inherits Window {
            width: 600px;
            height: 600px;
            Rectangle {background: red;}

            Timer {
                interval: 100ms;
                running: true;
                triggered => {
                    popup1.show();
                    self.running = false;
                }
            }

            popup1:= PopupWindow {
                width: parent.width;
                height: parent.height;
                Rectangle {background: blue;}

                init => {
                    GlobalProperties.popup-opened = true;
                }

                TouchArea {
                    clicked => {
                        popup1.close();
                    }
                }

                // Timer {
                //    interval: 100ms;
                //     running: true;
                //     triggered => {
                //         popup1.close();
                //         self.running = false;
                //     }
                // }
            }
        }
    }

    let app = App::new().unwrap();

    app.run().unwrap();
}
