// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

//! Ported from Flutter's `MacOSScrollViewFlingVelocityTracker` (velocity_tracker.dart), which is:
//! Copyright 2014 The Flutter Authors. All rights reserved.
//!
//! Use of the original source is governed by a BSD-style license; see
//! the "flutter" entry in THIRD_PARTY_LICENSES (or LICENSE-THIRD-PARTY).
//!
//! Original: <https://github.com/flutter/flutter/blob/d6bed8ff6135cdd414f14edc3063f761d47ca846/packages/flutter/lib/src/gestures/velocity_tracker.dart>
//!
//! A close approximation of macOS scroll view's fling velocity estimation
//! strategy. It uses the same weighted-average approach as the iOS tracker,
//! just with different blend weights

use super::fling::{BlendWeights, weighted_recent_velocity};
use super::ring_buffer::VelocityRingBuffer;
use super::{VelocityEstimate, VelocityTracker};
use crate::animations::Instant;
use crate::lengths::LogicalVector;

/// macOS blends mostly the middle segment, with less weight on the oldest
/// and newest ones: `[oldest, middle, newest]`.
const WEIGHTS: BlendWeights = [0.15, 0.65, 0.2];

#[derive(Default)]
pub(crate) struct MacOsVelocityTracker<const N: usize> {
    buffer: VelocityRingBuffer<N>,
}

impl<const N: usize> VelocityTracker for MacOsVelocityTracker<N> {
    fn push(&mut self, time: Instant, position_delta: LogicalVector) {
        self.buffer.push(time, position_delta);
    }

    fn last_time(&self) -> Option<Instant> {
        self.buffer.last_time()
    }

    fn estimate_velocity(&self) -> Option<VelocityEstimate> {
        if self.buffer.empty() {
            return None;
        }

        Some(VelocityEstimate {
            velocity: weighted_recent_velocity(&self.buffer, WEIGHTS),
            confidence: 1.0,
        })
    }
}

#[cfg(test)]
mod tests_macos_velocity_tracker {
    use super::*;
    use core::time::Duration;

    #[test]
    fn estimate_velocity_is_none_when_empty() {
        let tracker = MacOsVelocityTracker::<8>::default();
        assert!(tracker.estimate_velocity().is_none());
        assert_eq!(tracker.last_time(), None);
    }

    #[test]
    fn estimate_velocity_is_zero_with_a_single_sample() {
        let mut tracker = MacOsVelocityTracker::<8>::default();
        tracker.push(Instant::default(), LogicalVector::new(5.0, 5.0));

        let estimate = tracker.estimate_velocity().unwrap();
        assert_eq!(estimate.velocity, LogicalVector::default());
        assert_eq!(estimate.confidence, 1.0);
    }

    #[test]
    fn estimate_velocity_blends_the_last_three_segments() {
        let mut tracker = MacOsVelocityTracker::<8>::default();
        let base_time = Instant::default();

        // Same setup as the iOS test: segments of 100, 200, 300 px/s.
        tracker.push(base_time, LogicalVector::new(0.0, 0.0));
        tracker.push(base_time + Duration::from_millis(10), LogicalVector::new(1.0, 0.0));
        tracker.push(base_time + Duration::from_millis(20), LogicalVector::new(2.0, 0.0));
        tracker.push(base_time + Duration::from_millis(30), LogicalVector::new(3.0, 0.0));

        let estimate = tracker.estimate_velocity().unwrap();
        let [oldest, middle, newest] = [100.0, 200.0, 300.0];
        let expected = oldest * WEIGHTS[0] + middle * WEIGHTS[1] + newest * WEIGHTS[2];
        assert!((estimate.velocity.x - expected).abs() < 1e-3);
        assert_eq!(estimate.velocity.y, 0.0);
        assert_eq!(estimate.confidence, 1.0);
    }
}
