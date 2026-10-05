// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT
#import <UIKit/UIKit.h>

typedef void (^SlintTouchRecorder)(NSSet<UITouch *> *touches, UIEvent *event, NSInteger phase);
void install_slint_touch_forwarding(UIView *host, UIScrollView *viewport,
                                   BOOL nativeOnly, SlintTouchRecorder recorder);
