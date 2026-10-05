// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

//! Ported from Flutter's `VelocityTracker` (velocity_tracker.dart), which is:
//! Copyright 2014 The Flutter Authors. All rights reserved.
//!
//! Use of the original source is governed by a BSD-style license
//!
//! Original: <https://github.com/flutter/flutter/blob/d6bed8ff6135cdd414f14edc3063f761d47ca846/packages/flutter/lib/src/gestures/velocity_tracker.dart>
//!
//! Estimates a pointer's fling velocity from a short history of positions,
//! for use as the flickable's initial deceleration-animation velocity

#[cfg(any(test, target_os = "ios", target_os = "linux", target_os = "none", target_os = "macos"))]
mod fling;
#[cfg(any(
    test,
    not(any(target_os = "ios", target_os = "linux", target_os = "none", target_os = "macos"))
))]
mod general;
#[cfg(any(test, target_os = "ios", target_os = "linux", target_os = "none"))]
mod ios;
#[cfg(any(
    test,
    not(any(target_os = "ios", target_os = "linux", target_os = "none", target_os = "macos"))
))]
mod least_square;
#[cfg(any(test, target_os = "linux", target_os = "none"))]
mod legacy;
#[cfg(any(test, target_os = "macos"))]
mod macos;
mod ring_buffer;

#[cfg(not(any(
    target_os = "ios",
    target_os = "linux",
    target_os = "none",
    target_os = "macos"
)))]
pub(crate) use general::GeneralVelocityTracker;
#[cfg(target_os = "ios")]
pub(crate) use ios::IOsVelocityTracker;
#[cfg(any(target_os = "linux", target_os = "none"))]
pub(crate) use legacy::LegacyVelocityTracker;
#[cfg(target_os = "macos")]
pub(crate) use macos::MacOsVelocityTracker;

use crate::animations::Instant;
use crate::lengths::{LogicalPx, LogicalVector};
use core::time::Duration;
#[cfg(not(feature = "std"))]
use num_traits::Float;

// https://github.com/flutter/flutter/blob/d6bed8ff6135cdd414f14edc3063f761d47ca846/packages/flutter/lib/src/gestures/velocity_tracker.dart#L142-L145
//
// Trackers that expire idle samples consider the pointer stopped after this interval.
const ASSUME_POINTER_MOVE_STOPPED: Duration = Duration::from_millis(40);

/// Logical pixels per second. Always `f32`: with an integer `Coord`, a rate would be
/// truncated to whole pixels per second.
pub(crate) type Velocity = euclid::Vector2D<f32, LogicalPx>;

pub(crate) struct VelocityEstimate {
    pub(crate) velocity: Velocity,
    #[cfg_attr(not(test), expect(unused, reason = "Confidence is not yet considered"))]
    pub(crate) confidence: f32,
}

pub(crate) struct FlickPolicy {
    pub(crate) threshold_velocity: Velocity,
    pub(crate) minimum_launch_speed: f32,
}

impl FlickPolicy {
    pub(crate) fn can_flick(&self, axis: super::Dimension, launch: f32, threshold: f32) -> bool {
        let gate = match axis {
            super::Dimension::X => self.threshold_velocity.x,
            super::Dimension::Y => self.threshold_velocity.y,
        };
        gate.is_finite()
            && launch.is_finite()
            && gate.abs() >= threshold
            && launch.abs() > self.minimum_launch_speed
    }
}

trait VelocityEstimator {
    fn estimate_velocity_internal(&self) -> Option<VelocityEstimate>;
}

// VelocityEstimator stays module-private on purpose: it seals VelocityTracker so only the
// trackers defined in this module can implement it.
#[allow(private_bounds)]
pub(crate) trait VelocityTracker: VelocityEstimator {
    fn push(&mut self, time: Instant, position_delta: LogicalVector);
    fn last_time(&self) -> Option<Instant>;
    fn flick_policy(&self, estimate: &VelocityEstimate) -> FlickPolicy {
        FlickPolicy { threshold_velocity: estimate.velocity, minimum_launch_speed: 0. }
    }
    fn estimate_velocity(&self) -> Option<VelocityEstimate> {
        if crate::animations::current_tick() - self.last_time()? > ASSUME_POINTER_MOVE_STOPPED {
            return None;
        }
        self.estimate_velocity_internal()
    }
}
