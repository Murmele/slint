// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

//! Combines the Android-style (hard-clamped) and iOS-style (rubber-band
//! overscroll) flick simulations behind one type, so callers such as
//! `Flickable` don't need to know which concrete simulation is running.

use alloc::boxed::Box;
use core::pin::Pin;
use core::time::Duration;

use crate::Property;
use crate::animations::Instant;
use crate::animations::simulations::android::{AndroidFlick, AndroidFlickParameters};
use crate::animations::simulations::ios::{IOsFlick, IOsFlickParameters};
use crate::animations::simulations::scroll_spring::SpringSimulation;
use crate::animations::simulations::{Parameter, PositionSimulation, Simulation};
use crate::items::AutoBool;

/// Parameters to start a flick simulation from, independent of which
/// concrete simulation ends up running.
pub enum FlickSimulationParameter {
    /// Cover a fixed distance in a fixed duration, e.g. wheel scrolling.
    Distance { delta: f32, duration: Duration },
    /// Start from an estimated release velocity, e.g. a touch flick.
    Velocity { velocity: f32 },
}

/// Either an Android-style hard-clamped fling or an iOS-style rubber-band
/// fling. Wrapping both in one enum (rather than picking a single concrete
/// type at compile time) lets `create_simulation` choose per call, based on
/// the `bounce` property and platform, since that decision can change at
/// runtime even on a single platform (`bounce: on` forces iOS-style physics
/// anywhere).
pub enum FlickSimulation {
    Android(AndroidFlick),
    Ios(IOsFlick),
}

impl Simulation for FlickSimulation {
    fn step(&mut self, current: &mut f32, new_tick: Instant) -> bool {
        match self {
            FlickSimulation::Android(s) => s.step(current, new_tick),
            FlickSimulation::Ios(s) => s.step(current, new_tick),
        }
    }
}

impl PositionSimulation for FlickSimulation {
    fn remaining_distance(&self, time_elapsed: Duration) -> f32 {
        match self {
            FlickSimulation::Android(s) => s.remaining_distance(time_elapsed),
            FlickSimulation::Ios(s) => s.remaining_distance(time_elapsed),
        }
    }

    fn remaining_velocity(&self, time_elapsed: Duration) -> f32 {
        match self {
            FlickSimulation::Android(s) => s.remaining_velocity(time_elapsed),
            FlickSimulation::Ios(s) => s.remaining_velocity(time_elapsed),
        }
    }

    fn overshoot_allowed(&self) -> bool {
        match self {
            FlickSimulation::Android(s) => s.overshoot_allowed(),
            FlickSimulation::Ios(s) => s.overshoot_allowed(),
        }
    }
}

impl FlickSimulation {
    /// Whether to use the iOS-style (rubber-band overscroll) simulation rather
    /// than the Android-style (hard-clamped) one: forced on by `bounce: on`,
    /// forced off by `bounce: off`, and otherwise on exactly where iOS's own
    /// scroll views bounce.
    pub fn use_bounce(bounce: AutoBool) -> bool {
        match bounce {
            AutoBool::Auto => cfg!(target_os = "ios"),
            AutoBool::On => true,
            AutoBool::Off => false,
        }
    }

    /// Builds and starts the flick simulation for one axis, choosing between
    /// the Android and iOS physics based on `bounce` and the platform.
    pub fn create_simulation(
        simulation_parameter: FlickSimulationParameter,
        bounce: AutoBool,
        start_value: f32,
        limit_value: Pin<Box<Property<f32>>>,
    ) -> FlickSimulation {
        if Self::use_bounce(bounce) {
            let params = match simulation_parameter {
                FlickSimulationParameter::Velocity { velocity } => {
                    IOsFlickParameters::new(velocity)
                }
                FlickSimulationParameter::Distance { delta, duration } => {
                    IOsFlickParameters::new_with_distance(delta, duration)
                }
            };
            FlickSimulation::Ios(params.simulation(start_value, limit_value))
        } else {
            let params = match simulation_parameter {
                FlickSimulationParameter::Velocity { velocity } => {
                    AndroidFlickParameters::new_with_default_friction(velocity)
                }
                FlickSimulationParameter::Distance { delta, duration } => {
                    AndroidFlickParameters::new_with_distance(delta, duration)
                }
            };
            FlickSimulation::Android(params.simulation(start_value, limit_value))
        }
    }

    pub fn create_spring_simulation(
        start_value: f32,
        limit_value: Pin<Box<Property<f32>>>,
    ) -> SpringSimulation {
        SpringSimulation::new_with_default_parameters(start_value, limit_value)
    }
}
