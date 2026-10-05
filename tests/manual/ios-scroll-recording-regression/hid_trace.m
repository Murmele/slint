// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT

#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <mach/mach_time.h>
#import <dlfcn.h>
#import <math.h>

extern NSDictionary *hid_trace_view_state(void);

static NSMutableString *hidTrace;
static uint64_t dispatchID, ingressID, activeIngress;
static NSUInteger digitizerNodes;
static uint32_t (*getType)(const void *);
static uint64_t (*getTimestamp)(const void *);
static CFArrayRef (*getChildren)(const void *);
static double (*getFloat)(const void *, uint32_t);
static CFIndex (*getInteger)(const void *, uint32_t);
static CFDataRef (*createData)(CFAllocatorRef, const void *);
static void (*originalHIDHandler)(id, SEL, const void *);
static mach_timebase_info_data_t timebase;

static void appendRecord(NSDictionary *record)
{
    if (!hidTrace) return;
    NSData *json = [NSJSONSerialization dataWithJSONObject:record options:0 error:nil];
    if (json) [hidTrace appendFormat:@"%@\n", [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding]];
}

static double secondsForTicks(uint64_t ticks)
{
    return (double)((long double)ticks * timebase.numer / timebase.denom / 1e9L);
}

static void recordNode(const void *event, NSString *source, NSString *path, NSUInteger depth)
{
    if (!event || !getType || !getTimestamp || depth > 8) return;
    uint32_t type = getType(event);
    uint64_t ticks = getTimestamp(event);
    NSMutableDictionary *record = [@{@"kind": @"hid_node", @"source": source,
        @"dispatch_id": @(dispatchID), @"ingress_id": @(activeIngress), @"path": path,
        @"callback_seconds": @(CACurrentMediaTime()), @"timestamp_ticks": @(ticks),
        @"timestamp_seconds": @(secondsForTicks(ticks)), @"type": @(type),
        @"event_pointer": [NSString stringWithFormat:@"%p", event]} mutableCopy];
    if (type == 11 && getFloat && getInteger) {
        digitizerNodes++;
        NSMutableArray *fields = [NSMutableArray new];
        for (uint32_t offset = 0; offset < 32; ++offset) {
            uint32_t field = (11 << 16) | offset;
            double value = getFloat(event, field);
            [fields addObject:@{@"field": @(field), @"integer": @(getInteger(event, field)),
                @"float": isfinite(value) ? @(value) : NSNull.null}];
        }
        record[@"fields"] = fields;
        record[@"x"] = @(getFloat(event, 11 << 16));
        record[@"y"] = @(getFloat(event, (11 << 16) + 1));
    }
    if (createData && depth == 0) {
        CFDataRef data = createData(kCFAllocatorDefault, event);
        if (data) {
            record[@"raw_base64"] = [(__bridge NSData *)data base64EncodedStringWithOptions:0];
            CFRelease(data);
        }
    }
    appendRecord(record);
    CFArrayRef children = getChildren ? getChildren(event) : NULL;
    if (children) {
        for (CFIndex index = 0; index < CFArrayGetCount(children); ++index) {
            recordNode(CFArrayGetValueAtIndex(children, index), source,
                [path stringByAppendingFormat:@"/%ld", (long)index], depth + 1);
        }
    }
}

void record_hid_object(id object, const char *source)
{
    if (!hidTrace || !object) return;
    SEL selector = NSSelectorFromString(@"_hidEvent");
    if ([object respondsToSelector:selector]) {
        const void *event = ((const void *(*)(id, SEL))objc_msgSend)(object, selector);
        recordNode(event, [NSString stringWithUTF8String:source], @"root", 0);
    } else {
        appendRecord(@{@"kind": @"unavailable", @"source": [NSString stringWithUTF8String:source],
            @"class": NSStringFromClass([object class]), @"dispatch_id": @(dispatchID)});
    }
}

static void recordState(NSString *stage, UIEvent *event)
{
    NSMutableDictionary *state = [hid_trace_view_state() mutableCopy];
    state[@"kind"] = @"dispatch_state";
    state[@"stage"] = stage;
    state[@"dispatch_id"] = @(dispatchID);
    state[@"ingress_id"] = @(activeIngress);
    state[@"callback_seconds"] = @(CACurrentMediaTime());
    if (event) {
        state[@"event_timestamp"] = @(event.timestamp);
        NSMutableArray *touches = [NSMutableArray new];
        for (UITouch *touch in event.allTouches) {
            CGPoint point = [touch locationInView:nil];
            [touches addObject:@{@"identity": [NSString stringWithFormat:@"%p", touch],
                @"timestamp": @(touch.timestamp), @"phase": @(touch.phase),
                @"x": @(point.x), @"y": @(point.y)}];
        }
        state[@"touches"] = touches;
    }
    appendRecord(state);
}

static void probeHIDHandler(id application, SEL selector, const void *event)
{
    uint64_t previous = activeIngress;
    activeIngress = ++ingressID;
    recordNode(event, @"application_hid_ingress", @"root", 0);
    recordState(@"hid_before", nil);
    originalHIDHandler(application, selector, event);
    recordState(@"hid_after", nil);
    activeIngress = previous;
}

@interface UIApplication (SlintHIDProbe)
- (void)slint_probe_sendEvent:(UIEvent *)event;
@end

@implementation UIApplication (SlintHIDProbe)
- (void)slint_probe_sendEvent:(UIEvent *)event
{
    if (event.type != UIEventTypeTouches) {
        [self slint_probe_sendEvent:event];
        return;
    }
    ++dispatchID;
    record_hid_object(event, "ui_event_before_dispatch");
    recordState(@"send_before", event);
    uint64_t start = mach_absolute_time();
    [self slint_probe_sendEvent:event];
    recordState(@"send_after", event);
    appendRecord(@{@"kind": @"dispatch_duration", @"dispatch_id": @(dispatchID),
        @"duration_ms": @(secondsForTicks(mach_absolute_time() - start) * 1000)});
}
@end

void install_hid_trace(void)
{
    if (![NSProcessInfo.processInfo.environment[@"HID_TRACE"] boolValue] || hidTrace) return;
    hidTrace = [NSMutableString new];
    mach_timebase_info(&timebase);
    void *library = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_LAZY);
    void *symbols = library ?: RTLD_DEFAULT;
    getType = dlsym(symbols, "IOHIDEventGetType");
    getTimestamp = dlsym(symbols, "IOHIDEventGetTimeStamp");
    getChildren = dlsym(symbols, "IOHIDEventGetChildren");
    getFloat = dlsym(symbols, "IOHIDEventGetFloatValue");
    getInteger = dlsym(symbols, "IOHIDEventGetIntegerValue");
    createData = dlsym(symbols, "IOHIDEventCreateData");
    Class application = UIApplication.class;
    SEL handler = NSSelectorFromString(@"_handleHIDEvent:");
    Method method = class_getInstanceMethod(application, handler);
    BOOL hooked = NO;
    if (method && method_getNumberOfArguments(method) == 3) {
        char *argument = method_copyArgumentType(method, 2);
        char *result = method_copyReturnType(method);
        if (argument && argument[0] == '^' && result && result[0] == 'v') {
            originalHIDHandler = (void *)method_setImplementation(method, (IMP)probeHIDHandler);
            hooked = YES;
        }
        free(argument); free(result);
    }
    unsigned count = 0;
    Method *methods = class_copyMethodList(application, &count);
    NSMutableArray *hidMethods = [NSMutableArray new];
    for (unsigned index = 0; index < count; ++index) {
        NSString *name = NSStringFromSelector(method_getName(methods[index]));
        if ([name rangeOfString:@"hid" options:NSCaseInsensitiveSearch].location != NSNotFound)
            [hidMethods addObject:@{@"selector": name,
                @"encoding": @(method_getTypeEncoding(methods[index]))}];
    }
    free(methods);
    appendRecord(@{@"kind": @"capabilities", @"hid_ingress_hook": @(hooked),
        @"get_type": @(getType != NULL), @"get_timestamp": @(getTimestamp != NULL),
        @"get_children": @(getChildren != NULL), @"get_float": @(getFloat != NULL),
        @"get_integer": @(getInteger != NULL), @"raw_data": @(createData != NULL),
        @"timebase_numer": @(timebase.numer), @"timebase_denom": @(timebase.denom),
        @"hid_methods": hidMethods});
    method_exchangeImplementations(class_getInstanceMethod(application, @selector(sendEvent:)),
        class_getInstanceMethod(application, @selector(slint_probe_sendEvent:)));
}

void save_hid_trace(const char *directory, const char *scenario)
{
    if (!hidTrace) return;
    NSString *name = [NSString stringWithFormat:@"hid-%s.jsonl", scenario];
    [hidTrace writeToFile:[[NSString stringWithUTF8String:directory] stringByAppendingPathComponent:name]
        atomically:YES encoding:NSUTF8StringEncoding error:nil];
}

NSUInteger hid_digitizer_node_count(void) { return digitizerNodes; }

void record_hid_marker(NSString *name, NSDictionary *values)
{
    if (!hidTrace) return;
    NSMutableDictionary *record = [values mutableCopy];
    record[@"kind"] = name;
    record[@"callback_seconds"] = @(CACurrentMediaTime());
    record[@"dispatch_id"] = @(dispatchID);
    record[@"ingress_id"] = @(activeIngress);
    appendRecord(record);
}

void record_slint_touch(int32_t identity, uint8_t phase, double x, double y,
    uint64_t context_ns, uint64_t tick_ns, bool before)
{
    record_hid_marker(before ? @"slint_touch_before" : @"slint_touch_after",
        @{@"finger_id": @(identity), @"winit_phase": @(phase), @"x": @(x), @"y": @(y),
            @"context_ns": @(context_ns), @"animation_tick_ns": @(tick_ns)});
}
