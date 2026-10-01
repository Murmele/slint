// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

//! Ported from Flutter's `SpringSimulation` (physics/spring_simulation.dart), which is:
//! Copyright 2014 The Flutter Authors. All rights reserved.
//!
//! Use of the original source is governed by a BSD-style license
//!
//! Original: <https://github.com/flutter/flutter/blob/d6bed8ff6135cdd414f14edc3063f761d47ca846/packages/flutter/lib/src/physics/spring_simulation.dart>

use crate::animations::Instant;
use crate::animations::simulations::spring::{
    SpringParameters, SpringPhysicalParameters, SpringRegime,
};
use crate::animations::simulations::{PositionSimulation, Simulation};

#[cfg(test)]
use crate::animations::simulations::test_limit_property;

const DEFAULT_MASS: f32 = 0.5;
const DEFAULT_STIFFNESS: f32 = 100.;
const DEFAULT_RATIO: f32 = 1.1;

const ZERO_TOLERANCE: f32 = 1e-3;

// Fitted to the 200-point UIKit capture documented in the iOS comparison FINDINGS.md.
#[cfg(any(target_os = "ios", test))]
const EXPERIMENTAL_RETURN_RATE: f32 = 2.4422646;

#[derive(Debug)]
pub struct SpringSimulation {
    start_time: Instant,
    traveled: f32,
    data: SpringRegime,
    init_pos: f32,
    rubber_band_viewport: Option<f32>,
}

impl SpringSimulation {
    pub fn new_with_default_parameters(
        start_value: f32,
        limit_value: core::pin::Pin<alloc::boxed::Box<crate::Property<f32>>>,
    ) -> Self {
        let l = limit_value.as_ref().get();
        let (w_n, zeta) = SpringPhysicalParameters::new_with_damping_ratio(
            DEFAULT_MASS,
            DEFAULT_STIFFNESS,
            DEFAULT_RATIO,
        )
        .to_natural_frequency_and_damping_ratio();
        let init_pos = l - start_value;
        let spring = SpringRegime::new(init_pos, 0., w_n, zeta);

        Self {
            start_time: crate::animations::current_tick(),
            traveled: 0.,
            data: spring,
            init_pos,
            rubber_band_viewport: None,
        }
    }

    #[cfg(any(target_os = "ios", test))]
    pub fn new_with_rubber_band_parameters(
        start_value: f32,
        limit_value: core::pin::Pin<alloc::boxed::Box<crate::Property<f32>>>,
        viewport: f32,
    ) -> Self {
        Self::new_with_rubber_band_velocity(
            start_value,
            limit_value,
            viewport,
            EXPERIMENTAL_RETURN_RATE,
        )
    }

    #[cfg(any(target_os = "ios", test))]
    pub(crate) fn new_with_rubber_band_velocity(
        start_value: f32,
        limit_value: core::pin::Pin<alloc::boxed::Box<crate::Property<f32>>>,
        viewport: f32,
        return_rate: f32,
    ) -> Self {
        if viewport <= 0. {
            return Self::new_with_default_parameters(start_value, limit_value);
        }
        let displayed = limit_value.as_ref().get() - start_value;
        let compression = (1. - displayed.abs() / viewport).max(0.001);
        let init_pos = displayed / (0.55 * compression);
        let velocity = -init_pos * return_rate / compression;
        let (w_n, zeta) = SpringPhysicalParameters::new_with_damping_ratio(
            DEFAULT_MASS,
            DEFAULT_STIFFNESS,
            DEFAULT_RATIO,
        )
        .to_natural_frequency_and_damping_ratio();
        Self {
            start_time: crate::animations::current_tick(),
            traveled: 0.,
            data: SpringRegime::new(init_pos, velocity, w_n, zeta),
            init_pos,
            rubber_band_viewport: Some(viewport),
        }
    }

    #[cfg(any(target_os = "ios", test))]
    pub(crate) fn with_start_time(mut self, start_time: Instant) -> Self {
        self.start_time = start_time;
        self
    }

    fn display_travel(&self, raw_travel: f32) -> f32 {
        if let Some(viewport) = self.rubber_band_viewport {
            let travel = raw_travel.clamp(self.init_pos.min(0.), self.init_pos.max(0.));
            0.55 * travel * viewport / (viewport + 0.55 * travel.abs())
        } else {
            raw_travel
        }
    }

    fn step_internal(&mut self, current: &mut f32, new_tick: Instant) -> bool {
        let t = new_tick.duration_since(self.start_time).as_secs_f32();
        let (new_pos, new_vel) = self.data.evaluate(t);
        let new_traveled = self.display_travel(self.init_pos - new_pos);
        *current += new_traveled - self.traveled;
        self.traveled = new_traveled;

        new_pos.abs() < ZERO_TOLERANCE && new_vel.abs() < ZERO_TOLERANCE
    }
}

impl Simulation for SpringSimulation {
    fn step(&mut self, current: &mut f32, new_tick: Instant) -> bool {
        self.step_internal(current, new_tick)
    }
}

impl PositionSimulation for SpringSimulation {
    fn remaining_distance(&self, time_elapsed: core::time::Duration) -> f32 {
        let position = self.data.current_position(time_elapsed.as_secs_f32());
        if self.rubber_band_viewport.is_some() {
            self.display_travel(self.init_pos) - self.display_travel(self.init_pos - position)
        } else {
            position
        }
    }

    fn remaining_velocity(&self, time_elapsed: core::time::Duration) -> f32 {
        let t = time_elapsed.as_secs_f32();
        let velocity = -self.data.current_velocity(t);
        if let Some(viewport) = self.rubber_band_viewport {
            let progress = self.init_pos - self.data.current_position(t);
            if progress < self.init_pos.min(0.) || progress > self.init_pos.max(0.) {
                return 0.;
            }
            let scale = viewport / (viewport + 0.55 * progress.abs());
            velocity * 0.55 * scale * scale
        } else {
            velocity
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::animations::simulations::assert_approx_eq;
    use core::time::Duration;

    #[test]
    fn remaining_distance_and_velocity_settle_to_zero() {
        let simulation =
            SpringSimulation::new_with_default_parameters(30., test_limit_property(20.));
        assert_approx_eq!(simulation.remaining_distance(core::time::Duration::from_secs(10)), 0.);
        assert_approx_eq!(simulation.remaining_velocity(core::time::Duration::from_secs(10)), 0.);
    }

    /// `remaining_velocity` reports the velocity of the content position that `step` moves,
    /// not of the spring's internal, target-relative coordinate. Overscrolled past a lower
    /// limit (`start_value > limit`), the content must move down toward the limit, so its
    /// velocity is negative.
    #[test]
    fn remaining_velocity_points_toward_the_limit_from_above() {
        let simulation =
            SpringSimulation::new_with_default_parameters(30., test_limit_property(20.));
        for millis in [50, 100, 300] {
            let t = core::time::Duration::from_millis(millis);
            assert!(simulation.remaining_velocity(t) < 0., "{millis}ms");
        }
    }

    /// Mirrors [`remaining_velocity_points_toward_the_limit_from_above`]: overscrolled past an
    /// upper limit (`start_value < limit`), the content must move up toward the limit, so its
    /// velocity is positive.
    #[test]
    fn remaining_velocity_points_toward_the_limit_from_below() {
        let simulation =
            SpringSimulation::new_with_default_parameters(10., test_limit_property(20.));
        for millis in [50, 100, 300] {
            let t = core::time::Duration::from_millis(millis);
            assert!(simulation.remaining_velocity(t) > 0., "{millis}ms");
        }
    }
    #[test]
    fn rubber_band_spring_reports_the_velocity_it_displays() {
        for start in [-228.642, -92.069, 21.392, 228.642] {
            let simulation = SpringSimulation::new_with_rubber_band_parameters(
                start,
                test_limit_property(0.),
                774.,
            );
            assert_approx_eq!(simulation.remaining_distance(Duration::ZERO), -start);
            for millis in [50, 100, 200, 500] {
                let t = Duration::from_millis(millis);
                let dt = Duration::from_micros(100);
                let measured = -(simulation.remaining_distance(t + dt)
                    - simulation.remaining_distance(t - dt))
                    / (2. * dt.as_secs_f32());
                assert!((simulation.remaining_velocity(t) - measured).abs() < 0.2);
            }
            assert!(simulation.remaining_distance(Duration::from_secs(10)).abs() < 0.001);
        }
    }
    #[test]
    fn rubber_band_spring_honors_an_explicit_start_time() {
        let start = crate::animations::current_tick() + Duration::from_millis(8);
        let mut simulation = SpringSimulation::new_with_rubber_band_parameters(
            92.069,
            test_limit_property(0.),
            774.,
        )
        .with_start_time(start);
        let mut position = 92.069;
        simulation.step(&mut position, start);
        assert_approx_eq!(position, 92.069);
        simulation.step(&mut position, start + Duration::from_millis(100));
        assert!(position < 92.069 && position > 0.);
    }
}
