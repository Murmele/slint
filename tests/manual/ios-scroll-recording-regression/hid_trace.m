// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT

#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <mach/mach_time.h>
#import <dlfcn.h>
#import <math.h>
#import <stdatomic.h>

extern NSDictionary *hid_trace_view_state(void);

static NSMutableString *hidTrace;
static uint64_t dispatchID, ingressID, activeIngress;
static atomic_ulong digitizerNodes;
static atomic_ulong serializationErrors;
extern void handle_comparison_event(UIEvent *event, BOOL forward);
static dispatch_queue_t traceQueue;
static char traceQueueKey;
static const void *(*copyEvent)(CFAllocatorRef, const void *);
typedef struct { uint64_t dispatch, ingress; double callback; } PacketContext;
static uint32_t (*getType)(const void *);
static uint64_t (*getTimestamp)(const void *);
static CFArrayRef (*getChildren)(const void *);
static double (*getFloat)(const void *, uint32_t);
static CFIndex (*getInteger)(const void *, uint32_t);
static CFDataRef (*createData)(CFAllocatorRef, const void *);
static void (*originalHIDHandler)(id, SEL, const void *);
static mach_timebase_info_data_t timebase;

static id finiteNumber(double value)
{
    return isfinite(value) ? @(value) : NSNull.null;
}

static void serializeRecord(NSDictionary *record)
{
    @try {
        NSError *error = nil;
        NSData *json = [NSJSONSerialization dataWithJSONObject:record options:0 error:&error];
        if (!json) { atomic_fetch_add(&serializationErrors, 1); return; }
        [hidTrace appendFormat:@"%@\n", [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding]];
    } @catch (NSException *exception) {
        atomic_fetch_add(&serializationErrors, 1);
    }
}

static void appendRecord(NSDictionary *record)
{
    if (!hidTrace) return;
    NSDictionary *snapshot = [record copy];
    if (dispatch_get_specific(&traceQueueKey)) serializeRecord(snapshot);
    else dispatch_async(traceQueue, ^{ serializeRecord(snapshot); });
}

static double secondsForTicks(uint64_t ticks)
{
    return (double)((long double)ticks * timebase.numer / timebase.denom / 1e9L);
}

static void decodeNode(const void *event, NSString *source, NSString *path, NSUInteger depth, PacketContext context)
{
    if (!event || !getType || !getTimestamp || depth > 8) return;
    uint32_t type = getType(event);
    uint64_t ticks = getTimestamp(event);
    NSMutableDictionary *record = [@{@"kind": @"hid_node", @"source": source,
        @"dispatch_id": @(context.dispatch), @"ingress_id": @(context.ingress), @"path": path,
        @"callback_seconds": @(context.callback), @"timestamp_ticks": @(ticks),
        @"timestamp_seconds": @(secondsForTicks(ticks)), @"type": @(type),
        @"event_pointer": [NSString stringWithFormat:@"%p", event]} mutableCopy];
    if (type == 11 && getFloat && getInteger) {
        atomic_fetch_add(&digitizerNodes, 1);
        NSMutableArray *fields = [NSMutableArray new];
        for (uint32_t offset = 0; offset < 32; ++offset) {
            uint32_t field = (11 << 16) | offset;
            double value = getFloat(event, field);
            [fields addObject:@{@"field": @(field), @"integer": @(getInteger(event, field)),
                @"float": finiteNumber(value)}];
        }
        record[@"fields"] = fields;
        record[@"x"] = finiteNumber(getFloat(event, 11 << 16));
        record[@"y"] = finiteNumber(getFloat(event, (11 << 16) + 1));
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
            decodeNode(CFArrayGetValueAtIndex(children, index), source,
                [path stringByAppendingFormat:@"/%ld", (long)index], depth + 1, context);
        }
    }
}

static void capturePacket(const void *event, NSString *source)
{
    if (!event || !copyEvent) return;
    PacketContext context = { dispatchID, activeIngress, CACurrentMediaTime() };
    const void *snapshot = copyEvent(kCFAllocatorDefault, event);
    if (!snapshot) return;
    dispatch_async(traceQueue, ^{
        decodeNode(snapshot, source, @"root", 0, context);
        CFRelease(snapshot);
    });
}

void record_hid_object(id object, const char *source)
{
    if (!hidTrace || !object) return;
    SEL selector = NSSelectorFromString(@"_hidEvent");
    if ([object respondsToSelector:selector]) {
        const void *event = ((const void *(*)(id, SEL))objc_msgSend)(object, selector);
        capturePacket(event, [NSString stringWithUTF8String:source]);
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
                @"x": @(point.x), @"y": @(point.y),
                @"view_class": touch.view ? NSStringFromClass(touch.view.class) : NSNull.null}];
        }
        state[@"touches"] = touches;
    }
    appendRecord(state);
}

static void probeHIDHandler(id application, SEL selector, const void *event)
{
    uint64_t previous = activeIngress;
    activeIngress = ++ingressID;
    capturePacket(event, @"application_hid_ingress");
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
    uint64_t start = 0;
    if (hidTrace) {
        ++dispatchID;
        record_hid_object(event, "ui_event_before_dispatch");
        recordState(@"send_before", event);
        start = mach_absolute_time();
    }
    handle_comparison_event(event, NO);
    [self slint_probe_sendEvent:event];
    handle_comparison_event(event, YES);
    if (hidTrace) {
        recordState(@"send_after", event);
        appendRecord(@{@"kind": @"dispatch_duration", @"dispatch_id": @(dispatchID),
            @"duration_ms": @(secondsForTicks(mach_absolute_time() - start) * 1000)});
    }
}
@end

void install_hid_trace(void)
{
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        method_exchangeImplementations(class_getInstanceMethod(UIApplication.class, @selector(sendEvent:)),
            class_getInstanceMethod(UIApplication.class, @selector(slint_probe_sendEvent:)));
    });
    if (![NSProcessInfo.processInfo.environment[@"HID_TRACE"] isEqualToString:@"1"] || hidTrace) return;
    hidTrace = [NSMutableString new];
    traceQueue = dispatch_queue_create("dev.slint.hid-capture", DISPATCH_QUEUE_SERIAL);
    dispatch_queue_set_specific(traceQueue, &traceQueueKey, &traceQueueKey, NULL);
    appendRecord(@{@"kind": @"nonfinite_control", @"x": finiteNumber(NAN),
        @"y": finiteNumber(INFINITY), @"negative_infinity": finiteNumber(-INFINITY)});
    mach_timebase_info(&timebase);
    void *library = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_LAZY);
    void *symbols = library ?: RTLD_DEFAULT;
    copyEvent = dlsym(symbols, "IOHIDEventCreateCopy");
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
        @"copy_event": @(copyEvent != NULL), @"get_type": @(getType != NULL), @"get_timestamp": @(getTimestamp != NULL),
        @"get_children": @(getChildren != NULL), @"get_float": @(getFloat != NULL),
        @"get_integer": @(getInteger != NULL), @"raw_data": @(createData != NULL),
        @"timebase_numer": @(timebase.numer), @"timebase_denom": @(timebase.denom),
        @"hid_methods": hidMethods});
}

void save_hid_trace(const char *directory, const char *scenario)
{
    if (!hidTrace) return;
    NSString *name = [NSString stringWithFormat:@"hid-%s.jsonl", scenario];
    __block NSString *snapshot;
    dispatch_sync(traceQueue, ^{ snapshot = [hidTrace copy]; });
    [snapshot writeToFile:[[NSString stringWithUTF8String:directory] stringByAppendingPathComponent:name]
        atomically:YES encoding:NSUTF8StringEncoding error:nil];
}

NSUInteger hid_digitizer_node_count(void) { return atomic_load(&digitizerNodes); }

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

NSUInteger hid_serialization_error_count(void) { return atomic_load(&serializationErrors); }

void record_slint_render(bool after, uint64_t context_ns, uint64_t tick_ns, float offset)
{
    record_hid_marker(after ? @"slint_render_after" : @"slint_render_before",
        @{@"context_ns": @(context_ns), @"animation_tick_ns": @(tick_ns), @"offset": finiteNumber(offset)});
}
