// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT

#import <Foundation/Foundation.h>

BOOL synthesizeRapidFlicksWithGap(pid_t processID, double width, double height, int count,
                                  double interFlickGap);

BOOL synthesizePanProbe(pid_t processID, double width, double height, const double *times,
                        const double *xOffsets, const double *yOffsets, int pointCount,
                        double holdDuration);

BOOL synthesizeOverscrollPull(pid_t processID, double width, double height, double distance,
                              double duration, double holdDuration);

BOOL synthesizeRecordedSequence(pid_t processID, double width, double height,
    const double *times, const double *xs, const double *ys,
    const int *starts, const int *counts, int gestureCount);
