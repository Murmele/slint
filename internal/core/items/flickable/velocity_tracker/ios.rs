// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

//! Ported from Flutter's `IOSScrollViewFlingVelocityTracker` (velocity_tracker.dart), which is:
//! Copyright 2014 The Flutter Authors. All rights reserved.
//!
//! Use of the original source is governed by a BSD-style license
//!
//! Original: <https://github.com/flutter/flutter/blob/d6bed8ff6135cdd414f14edc3063f761d47ca846/packages/flutter/lib/src/gestures/velocity_tracker.dart>
//!
//! A close approximation of iOS scroll view's fling velocity estimation
//! strategy: a weighted average of the last few point-to-point velocities

use super::fling::{BlendWeights, weighted_recent_velocity};
use super::ring_buffer::VelocityRingBuffer;
use super::{VelocityEstimate, VelocityEstimator, VelocityTracker};
use crate::animations::Instant;
use crate::lengths::LogicalVector;

///                        [oldest, middle, newest]`.
const WEIGHTS: BlendWeights = [0.6, 0.35, 0.05];
const PAN_WEIGHTS: BlendWeights = [0., 0.8, 0.2];
/// `weighted_recent_velocity` reads one more sample than there are weights
/// (each weight blends a segment between two consecutive samples).
const REQUIRED_SAMPLES: usize = WEIGHTS.len() + 1;

#[derive(Default, Debug)]
pub(crate) struct IOsVelocityTracker<const NATIVE_IOS: bool = false> {
    buffer: VelocityRingBuffer<REQUIRED_SAMPLES>,
}

impl<const NATIVE_IOS: bool> IOsVelocityTracker<NATIVE_IOS> {
    fn blended_velocity(&self, mut weights: BlendWeights) -> super::Velocity {
        let missing = weights.len().saturating_sub(self.buffer.len().saturating_sub(1));
        if NATIVE_IOS && missing < weights.len() {
            weights[missing] += weights[..missing].iter().sum::<f32>();
            weights[..missing].fill(0.);
        }
        weighted_recent_velocity(&self.buffer, weights)
    }
}

impl<const NATIVE_IOS: bool> VelocityTracker for IOsVelocityTracker<NATIVE_IOS> {
    fn push(&mut self, time: Instant, position_delta: LogicalVector) {
        self.buffer.push(time, position_delta);
    }

    fn last_time(&self) -> Option<Instant> {
        self.buffer.last_time()
    }
}

impl<const NATIVE_IOS: bool> VelocityEstimator for IOsVelocityTracker<NATIVE_IOS> {
    const EXPIRES_WHEN_IDLE: bool = !NATIVE_IOS;
    fn estimate_velocity_internal(&self) -> Option<VelocityEstimate> {
        let velocity = self.blended_velocity(WEIGHTS);
        Some(VelocityEstimate {
            velocity,
            threshold_velocity: if NATIVE_IOS {
                self.blended_velocity(PAN_WEIGHTS)
            } else {
                velocity
            },
            minimum_launch_speed: if NATIVE_IOS {
                crate::animations::simulations::ios::DECELERATION_STOP_VELOCITY
            } else {
                0.
            },
            confidence: 1.0,
        })
    }
}

#[cfg(test)]
mod tests_ios_velocity_tracker {
    use super::super::Velocity;
    use super::*;
    use core::time::Duration;

    #[test]
    fn native_ios_retains_velocity_without_new_samples_but_other_targets_expire() {
        let mut native = IOsVelocityTracker::<true>::default();
        let mut legacy = IOsVelocityTracker::<false>::default();
        for (millis, delta) in [(0, 0.), (10, 5.), (20, 5.), (30, 5.)] {
            native.push(Instant::from_millis(millis), LogicalVector::new(0., delta));
            legacy.push(Instant::from_millis(millis), LogicalVector::new(0., delta));
        }
        crate::animations::update_animations(Instant::from_millis(330));
        let estimate = native.estimate_velocity().unwrap();
        assert_eq!(estimate.velocity.y, 500.);
        assert_eq!(estimate.threshold_velocity.y, 500.);
        assert!(legacy.estimate_velocity().is_none());
    }

    #[test]
    fn native_ios_stationary_samples_close_the_release_gate() {
        let mut tracker = IOsVelocityTracker::<true>::default();
        for (millis, delta) in [(0, 0.), (10, 5.), (20, 5.), (30, 5.), (80, 0.), (130, 0.)] {
            tracker.push(Instant::from_millis(millis), LogicalVector::new(0., delta));
        }
        crate::animations::update_animations(Instant::from_millis(430));
        let estimate = tracker.estimate_velocity().unwrap();
        assert_eq!(estimate.threshold_velocity.y, 0.);
        assert!(!estimate.can_flick(estimate.velocity.y, estimate.threshold_velocity.y, 250.));
    }

    #[test]
    fn estimate_velocity_is_none_when_empty() {
        let tracker = IOsVelocityTracker::<false>::default();
        assert!(tracker.estimate_velocity().is_none());
        assert_eq!(tracker.last_time(), None);
    }

    #[test]
    fn estimate_velocity_is_zero_with_a_single_sample() {
        let mut tracker = IOsVelocityTracker::<false>::default();
        tracker.push(Instant::default(), LogicalVector::new(5.0, 5.0));

        let estimate = tracker.estimate_velocity().unwrap();
        assert_eq!(estimate.velocity, Velocity::default());
        assert_eq!(estimate.confidence, 1.0);
    }

    #[test]
    fn estimate_velocity_blends_the_last_three_segments() {
        let mut tracker = IOsVelocityTracker::<false>::default();
        let base_time = crate::animations::current_tick();

        // 4 samples, 10ms apart; the first sample's delta is never used
        // (there's no earlier sample to pair it with), leaving 3 segments
        // of 1.0, 2.0, and 3.0 px per 10ms, i.e. 100, 200, 300 px/s.
        tracker.push(base_time, LogicalVector::new(0.0, 0.0));
        tracker.push(base_time + Duration::from_millis(10), LogicalVector::new(1.0, 0.0));
        tracker.push(base_time + Duration::from_millis(20), LogicalVector::new(2.0, 0.0));
        tracker.push(base_time + Duration::from_millis(30), LogicalVector::new(3.0, 0.0));
        crate::animations::update_animations(base_time + Duration::from_millis(30));

        let estimate = tracker.estimate_velocity().unwrap();
        let [oldest, middle, newest] = [100.0, 200.0, 300.0];
        let expected = oldest * WEIGHTS[0] + middle * WEIGHTS[1] + newest * WEIGHTS[2];
        assert!((estimate.velocity.x - expected).abs() < 1e-3);
        assert_eq!(estimate.velocity.y, 0.0);
        assert_eq!(estimate.confidence, 1.0);
    }

    #[test]
    fn accelerating_flick_uses_pan_speed_to_start_slower_scroll() {
        let start = crate::animations::current_tick();
        let mut tracker = IOsVelocityTracker::<true>::default();
        tracker.push(start, LogicalVector::default());
        for (millis, delta) in [(10, -0.8), (20, -0.8), (30, -18.)] {
            tracker.push(start + Duration::from_millis(millis), LogicalVector::new(0., delta));
        }
        crate::animations::update_animations(start + Duration::from_millis(30));
        let estimate = tracker.estimate_velocity().unwrap();
        assert!((estimate.threshold_velocity.y + 424.).abs() < 0.01);
        assert!((estimate.velocity.y + 166.).abs() < 0.01);
        assert!(estimate.can_flick(estimate.velocity.y, estimate.threshold_velocity.y, 250.));
        assert!(estimate.velocity.y.abs() < 250.);
    }

    #[test]
    fn two_primary_segments_match_recorded_sparse_flick() {
        let start = crate::animations::current_tick();
        let mut tracker = IOsVelocityTracker::<true>::default();
        tracker.push(start, LogicalVector::default());
        tracker.push(start + Duration::from_micros(58425), LogicalVector::new(0., -20.));
        tracker.push(start + Duration::from_micros(75122), LogicalVector::new(0., -10.667));
        crate::animations::update_animations(start + Duration::from_micros(75122));
        let estimate = tracker.estimate_velocity().unwrap();
        assert!((estimate.threshold_velocity.y + 401.623).abs() < 0.1);
        assert!((estimate.velocity.y + 357.146).abs() < 0.1);
    }

    #[test]
    fn native_direction_disagreement_matches_uikit_but_stopped_launches_are_rejected() {
        for (segments, should_flick) in
            [([400., -300., -300.], true), ([190., -300., -300.], false)]
        {
            let start = crate::animations::current_tick();
            let mut tracker = IOsVelocityTracker::<true>::default();
            tracker.push(start, LogicalVector::default());
            for (index, speed) in segments.into_iter().enumerate() {
                tracker.push(
                    start + Duration::from_millis((index as u64 + 1) * 10),
                    LogicalVector::new(0., speed * 0.01),
                );
            }
            crate::animations::update_animations(start + Duration::from_millis(30));
            let estimate = tracker.estimate_velocity().unwrap();
            assert!((estimate.threshold_velocity.y + 300.).abs() < 0.01);
            assert_eq!(
                estimate.can_flick(estimate.velocity.y, estimate.threshold_velocity.y, 250.),
                should_flick
            );
        }
    }

    #[test]
    fn non_ios_sparse_samples_keep_the_existing_launch_and_gate() {
        for (moves, expected) in [(1, 20.), (2, 160.)] {
            let start = crate::animations::current_tick();
            let mut tracker = IOsVelocityTracker::<false>::default();
            tracker.push(start, LogicalVector::default());
            for index in 1..=moves {
                tracker.push(start + Duration::from_millis(index * 10), LogicalVector::new(4., 0.));
            }
            crate::animations::update_animations(start + Duration::from_millis(moves * 10));
            let estimate = tracker.estimate_velocity().unwrap();
            assert!((estimate.velocity.x - expected).abs() < 0.01);
            assert_eq!(estimate.threshold_velocity, estimate.velocity);
            assert_eq!(
                estimate.can_flick(estimate.velocity.x, estimate.threshold_velocity.x, 50.),
                moves == 2
            );
        }
    }

    #[test]
    fn carried_motion_can_make_a_small_native_launch_move() {
        let estimate = VelocityEstimate {
            velocity: Velocity::new(0., 6.),
            threshold_velocity: Velocity::new(0., 300.),
            minimum_launch_speed: 10.,
            confidence: 1.,
        };
        assert!(!estimate.can_flick(6., 300., 250.));
        assert!(estimate.can_flick(306., 300., 250.));
    }
}
