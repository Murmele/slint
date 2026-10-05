// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT
#import "ios-scroll-touch-forwarding.h"
#import <objc/runtime.h>

static __weak UIView *slintHost;
static __weak UIScrollView *nativeViewport;
static BOOL nativeOnlyInput;
static SlintTouchRecorder recordTouches;
static NSMutableSet<NSNumber *> *activeTouches;

static void handleEvent(UIEvent *event, BOOL forward)
{
    UIScrollView *viewport = nativeViewport;
    if (!viewport) return;
    for (NSInteger phase = 0; phase < 4; ++phase) {
        NSMutableSet<UITouch *> *touches = [NSMutableSet new];
        UITouchPhase nativePhase = phase == 2 ? UITouchPhaseEnded
                : phase == 3 ? UITouchPhaseCancelled : (UITouchPhase)phase;
        for (UITouch *touch in event.allTouches) {
            NSNumber *identity = @((uintptr_t)(__bridge void *)touch);
            if (touch.phase == UITouchPhaseBegan
                    && CGRectContainsPoint(viewport.bounds, [touch locationInView:viewport]))
                [activeTouches addObject:identity];
            if (touch.phase == nativePhase && [activeTouches containsObject:identity])
                [touches addObject:touch];
        }
        if (!touches.count) continue;
        if (!forward) {
            recordTouches(touches, event, phase);
        } else {
            if (!nativeOnlyInput) {
                switch (phase) {
                case 0: [slintHost touchesBegan:touches withEvent:event]; break;
                case 1: [slintHost touchesMoved:touches withEvent:event]; break;
                case 2: [slintHost touchesEnded:touches withEvent:event]; break;
                case 3: [slintHost touchesCancelled:touches withEvent:event]; break;
                }
            }
            if (phase == 2 || phase == 3)
                for (UITouch *touch in touches)
                    [activeTouches removeObject:@((uintptr_t)(__bridge void *)touch)];
        }
    }
}

@interface UIApplication (SlintComparisonInput)
- (void)slint_comparison_sendEvent:(UIEvent *)event;
@end
@implementation UIApplication (SlintComparisonInput)
- (void)slint_comparison_sendEvent:(UIEvent *)event
{
    if (event.type != UIEventTypeTouches) {
        [self slint_comparison_sendEvent:event];
        return;
    }
    handleEvent(event, NO);
    [self slint_comparison_sendEvent:event];
    handleEvent(event, YES);
}
@end

void install_slint_touch_forwarding(UIView *host, UIScrollView *viewport,
                                   BOOL nativeOnly, SlintTouchRecorder recorder)
{
    slintHost = host;
    nativeViewport = viewport;
    nativeOnlyInput = nativeOnly;
    recordTouches = [recorder copy];
    activeTouches = [NSMutableSet new];
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        method_exchangeImplementations(class_getInstanceMethod(UIApplication.class, @selector(sendEvent:)),
            class_getInstanceMethod(UIApplication.class, @selector(slint_comparison_sendEvent:)));
    });
}
