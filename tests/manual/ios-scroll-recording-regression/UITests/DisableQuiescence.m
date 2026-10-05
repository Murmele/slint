// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT
// cspell:ignore NSUInteger autoreleasing evaluatedObject instancetype nonatomic

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

@interface XCPointerEventPath : NSObject
- (instancetype)initForTouchAtPoint:(CGPoint)point offset:(double)offset;
- (void)moveToPoint:(CGPoint)point atOffset:(double)offset;
- (void)liftUpAtOffset:(double)offset;
@end

@interface XCSynthesizedEventRecord : NSObject
@property (nonatomic) pid_t targetProcessID;
- (instancetype)initWithName:(NSString *)name
        interfaceOrientation:(UIInterfaceOrientation)orientation;
- (void)addPointerEventPath:(XCPointerEventPath *)path;
- (BOOL)synthesizeWithError:(NSError **)error;
@end

BOOL synthesizeRapidFlicksWithGap(pid_t processID, double width, double height, int count,
                                  double interFlickGap)
{
    XCSynthesizedEventRecord *record =
            [[XCSynthesizedEventRecord alloc] initWithName:@"Rapid repeated hard flicks"
                                      interfaceOrientation:UIInterfaceOrientationPortrait];
    record.targetProcessID = processID;

    double startTime = 0;
    CGPoint start = CGPointMake(width * 0.5, height * 0.75);
    CGPoint end = CGPointMake(width * 0.5, height * 0.30);
    for (int flick = 0; flick < count; flick++) {
        XCPointerEventPath *path = [[XCPointerEventPath alloc] initForTouchAtPoint:start
                                                                            offset:startTime];
        for (int step = 1; step <= 5; step++) {
            CGFloat progress = step / 5.0;
            CGPoint point = CGPointMake(start.x, start.y + (end.y - start.y) * progress);
            [path moveToPoint:point atOffset:startTime + step * 0.012];
        }
        [path liftUpAtOffset:startTime + 0.065];
        [record addPointerEventPath:path];
        startTime += 0.065 + interFlickGap;
    }

    NSError *error = nil;
    BOOL result = [record synthesizeWithError:&error];
    if (!result)
        NSLog(@"Rapid flick synthesis failed: %@", error);
    return result;
}

static BOOL synthesizePanProbeAtPoint(pid_t processID, CGPoint start, const double *times,
                        const double *xOffsets, const double *yOffsets, int pointCount,
                        double holdDuration)
{
    if (pointCount < 1)
        return NO;
    XCSynthesizedEventRecord *record =
            [[XCSynthesizedEventRecord alloc] initWithName:@"UIKit pan recognition probe"
                                      interfaceOrientation:UIInterfaceOrientationPortrait];
    record.targetProcessID = processID;

    XCPointerEventPath *path = [[XCPointerEventPath alloc] initForTouchAtPoint:start offset:0];
    for (int point = 0; point < pointCount; point++) {
        CGPoint location = CGPointMake(start.x + xOffsets[point], start.y + yOffsets[point]);
        [path moveToPoint:location atOffset:times[point]];
    }
    [path liftUpAtOffset:times[pointCount - 1] + holdDuration];
    [record addPointerEventPath:path];

    NSError *error = nil;
    BOOL result = [record synthesizeWithError:&error];
    if (!result)
        NSLog(@"Pan recognition probe synthesis failed: %@", error);
    return result;
}

BOOL synthesizePanProbe(pid_t processID, double width, double height, const double *times,
                        const double *xOffsets, const double *yOffsets, int pointCount,
                        double holdDuration)
{
    return synthesizePanProbeAtPoint(processID, CGPointMake(width * 0.5, height * 0.72),
                                     times, xOffsets, yOffsets, pointCount, holdDuration);
}

BOOL synthesizeOverscrollPull(pid_t processID, double width, double height, double distance,
                              double duration, double holdDuration)
{
    const int count = MAX(1, (int)ceil(duration * 60));
    double times[count], xOffsets[count], yOffsets[count];
    for (int point = 0; point < count; point++) {
        double progress = (point + 1.0) / count;
        times[point] = 0.08 + duration * progress;
        xOffsets[point] = 0;
        yOffsets[point] = distance * progress;
    }
    return synthesizePanProbeAtPoint(processID, CGPointMake(width * 0.20, height * 0.18),
                                     times, xOffsets, yOffsets, count, holdDuration);
}


BOOL synthesizeRecordedSequence(pid_t processID, double width, double height,
    const double *times, const double *xs, const double *ys,
    const int *starts, const int *counts, int gestureCount)
{
    NSTimeInterval wallStart = NSProcessInfo.processInfo.systemUptime;
    for (int gesture = 0; gesture < gestureCount; ++gesture) {
        int start = starts[gesture], count = counts[gesture];
        double remaining = wallStart + times[start] - NSProcessInfo.processInfo.systemUptime;
        if (remaining > 0) [NSThread sleepForTimeInterval:remaining];
        XCSynthesizedEventRecord *record = [[XCSynthesizedEventRecord alloc]
            initWithName:@"Recorded gesture in sequential replay"
            interfaceOrientation:UIInterfaceOrientationPortrait];
        record.targetProcessID = processID;
        CGPoint point = CGPointMake(xs[start] * width / 428., ys[start] * height / 926.);
        XCPointerEventPath *path = [[XCPointerEventPath alloc] initForTouchAtPoint:point offset:0];
        for (int i = start + 1; i < start + count; ++i) {
            point = CGPointMake(xs[i] * width / 428., ys[i] * height / 926.);
            [path moveToPoint:point atOffset:times[i] - times[start]];
        }
        [path liftUpAtOffset:times[start + count - 1] - times[start]];
        [record addPointerEventPath:path];
        NSError *error = nil;
        if (![record synthesizeWithError:&error]) {
            NSLog(@"Recorded gesture injection failed: %@", error);
            return NO;
        }
    }
    return YES;
}
