use core::{f32::consts::PI, time::Duration};

// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0
use crate::{
    Coord,
    animations::{self, Instant},
};
use euclid::{Length, Scale};

pub enum Seconds {}
type Time = Length<f32, Seconds>;

#[derive(Debug)]
enum Direction {
    Increasing,
    Decreasing,
}

pub trait Simulation<Unit> {
    fn step(&mut self) -> (Length<Coord, Unit>, bool);
    fn curr_value(&self) -> Length<Coord, Unit>;
}

pub trait Parameter<Unit> {
    type Output;
    fn simulation(
        self,
        start_value: Length<Coord, Unit>,
        limit_value: Length<Coord, Unit>,
    ) -> Self::Output;
}

#[derive(Debug, Clone)]
pub struct ConstantDecelerationParameters<DestUnit> {
    pub initial_velocity: Length<f32, DestUnit>,
    pub deceleration: Scale<f32, Seconds, DestUnit>,
}

impl<DestUnit> Parameter<DestUnit> for ConstantDecelerationParameters<DestUnit> {
    type Output = ConstantDeceleration<DestUnit>;
    fn simulation(
        self,
        start_value: Length<Coord, DestUnit>,
        limit_value: Length<Coord, DestUnit>,
    ) -> Self::Output {
        let initial_velocity = self.initial_velocity.clone();
        ConstantDeceleration::new(start_value, limit_value, initial_velocity, self)
    }
}

#[derive(Debug)]
pub struct ConstantDeceleration<Unit> {
    /// If the limit is not reached, it is also fine. Also exceeding the limit can be ok,
    /// but at the end of the animation the limit shall not be exceeded
    limit_value: Length<Coord, Unit>,
    curr_val: Length<Coord, Unit>,
    velocity: Length<f32, Unit>,
    data: ConstantDecelerationParameters<Unit>,
    direction: Direction,
    start_time: Instant,
}

impl<Unit> ConstantDeceleration<Unit> {
    pub fn new(
        start_value: Length<Coord, Unit>,
        limit_value: Length<Coord, Unit>,
        initial_velocity: Length<f32, Unit>,
        data: ConstantDecelerationParameters<Unit>,
    ) -> Self {
        Self::new_internal(
            start_value,
            limit_value,
            initial_velocity,
            data,
            crate::animations::current_tick(),
        )
    }

    fn new_internal(
        start_value: Length<Coord, Unit>,
        limit_value: Length<Coord, Unit>,
        mut initial_velocity: Length<f32, Unit>,
        mut data: ConstantDecelerationParameters<Unit>,
        start_time: Instant,
    ) -> Self {
        let direction = if start_value < limit_value {
            data.deceleration = Scale::new(f32::abs(data.deceleration.0));
            assert!(initial_velocity.0 >= 0.); // Makes no sense yet that the velocity goes into the other direction
            initial_velocity = Length::new(f32::abs(initial_velocity.0));
            Direction::Increasing
        } else {
            data.deceleration = Scale::new(-f32::abs(data.deceleration.0));
            initial_velocity = Length::new(-f32::abs(initial_velocity.0));
            assert!(initial_velocity.0 <= 0.);
            Direction::Decreasing
        };

        Self {
            limit_value,
            curr_val: start_value,
            velocity: initial_velocity,
            data,
            direction,
            start_time,
        }
    }

    fn step_internal(&mut self, new_tick: Instant) -> (Length<Coord, Unit>, bool) {
        // We have to prevent go go beyond the limit where velocity gets zero
        let duration = Time::new(f32::min(
            new_tick.duration_since(self.start_time).as_secs_f32(),
            f32::abs((self.velocity / self.data.deceleration).0),
        ));

        self.start_time = new_tick;

        let new_velocity = self.velocity - duration * self.data.deceleration;

        self.curr_val += Length::new(
            (duration * Scale::<f32, Seconds, Unit>::new((self.velocity + new_velocity).0 / 2.)).0
                as Coord,
        ); // Trapezoidal integration
        self.velocity = new_velocity;

        match self.direction {
            Direction::Increasing => {
                if self.curr_val >= self.limit_value {
                    self.curr_val = self.limit_value;
                    self.velocity = Length::new(0.);
                    return (self.curr_val, true);
                } else if self.velocity.0 <= 0. {
                    return (self.curr_val, true);
                }
            }
            Direction::Decreasing => {
                if self.curr_val <= self.limit_value {
                    self.curr_val = self.limit_value;
                    self.velocity = Length::new(0.);
                    return (self.curr_val, true);
                } else if self.velocity.0 >= 0. {
                    return (self.curr_val, true);
                }
            }
        }
        (self.curr_val, false)
    }
}

impl<Unit> Simulation<Unit> for ConstantDeceleration<Unit> {
    fn curr_value(&self) -> Length<Coord, Unit> {
        self.curr_val
    }

    fn step(&mut self) -> (Length<Coord, Unit>, bool) {
        let new_tick = animations::current_tick();
        self.step_internal(new_tick)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::lengths::LogicalPx;
    use core::time::Duration;

    /// The velocity becomes zero before we are reaching the limit
    /// start_value < limit_value
    #[test]
    fn constant_deceleration_increasing_limit_not_reached() {
        const START_VALUE: f32 = 10.;
        const LIMIT_VALUE: f32 = 2000.;
        const INITIAL_VELOCITY: f32 = 50.;
        const DECELERATION: f32 = 20.;
        let parameters = ConstantDecelerationParameters::<LogicalPx> {
            initial_velocity: Length::new(INITIAL_VELOCITY),
            deceleration: Scale::new(DECELERATION),
        };

        let mut time = Instant::now();
        let mut simulation = ConstantDeceleration::new_internal(
            Length::new(START_VALUE),
            Length::new(LIMIT_VALUE),
            parameters.initial_velocity,
            parameters,
            time.clone(),
        );

        // Velocity does not become zero
        let mut duration = Duration::from_secs(1);
        assert!(DECELERATION * duration.as_secs_f32() < INITIAL_VELOCITY);
        time += duration;
        let (res, finished) = simulation.step_internal(time);
        assert_eq!(finished, false);
        assert_eq!(
            res.0,
            START_VALUE + INITIAL_VELOCITY * duration.as_secs_f32()
                - 0.5 * DECELERATION * duration.as_secs_f32().powi(2)
        );

        // Now the velocity becomes zero and we don't do any further calculations
        duration = Duration::from_hours(10);
        assert!(Duration::from_secs((INITIAL_VELOCITY / DECELERATION) as u64) < duration);
        time += duration;
        let (res, finished) = simulation.step_internal(time);
        assert_eq!(finished, true);
        assert_eq!(
            res.0,
            START_VALUE + INITIAL_VELOCITY * INITIAL_VELOCITY / DECELERATION
                - 0.5 * DECELERATION * (INITIAL_VELOCITY / DECELERATION).powi(2)
        );

        assert!(res.0 < LIMIT_VALUE); // We reached velocity zero before we reached the position limit
    }

    /// We reach the position limit before the velocity got zero
    #[test]
    fn constant_deceleration_increasing_limit_reached() {
        const START_VALUE: f32 = 10.;
        const LIMIT_VALUE: f32 = 20.;
        const INITIAL_VELOCITY: f32 = 50.;
        const DECELERATION: f32 = 20.;
        let parameters = ConstantDecelerationParameters::<LogicalPx> {
            initial_velocity: Length::new(INITIAL_VELOCITY),
            deceleration: Scale::new(DECELERATION),
        };

        let mut time = Instant::now();
        let mut simulation = ConstantDeceleration::new_internal(
            Length::new(START_VALUE),
            Length::new(LIMIT_VALUE),
            parameters.initial_velocity,
            parameters,
            time.clone(),
        );

        let duration = Duration::from_secs(1);
        assert!(f32::abs(DECELERATION * duration.as_secs_f32()) < f32::abs(INITIAL_VELOCITY)); // We don't reach the limit where the velocity gets zero
        time += duration;
        let (res, finished) = simulation.step_internal(time);
        assert_eq!(finished, true);
        assert_eq!(res.0, LIMIT_VALUE); // Limit reached
    }

    /// We don't reach the position limit. Before the velocity gets zero
    /// start_value > limit_value
    #[test]
    fn constant_deceleration_decreasing_limit_not_reached() {
        const START_VALUE: f32 = 2000.;
        const LIMIT_VALUE: f32 = 10.;
        const INITIAL_VELOCITY: f32 = -50.;
        const DECELERATION: f32 = 20.;

        let parameters = ConstantDecelerationParameters::<LogicalPx> {
            initial_velocity: Length::new(INITIAL_VELOCITY),
            deceleration: Scale::new(DECELERATION),
        };

        let mut time = Instant::now();
        let mut simulation = ConstantDeceleration::new_internal(
            Length::new(START_VALUE),
            Length::new(LIMIT_VALUE),
            parameters.initial_velocity,
            parameters,
            time.clone(),
        );

        let mut duration = Duration::from_secs(1);
        assert!(f32::abs(DECELERATION * duration.as_secs_f32()) < f32::abs(INITIAL_VELOCITY));
        time += duration;
        let (res, finished) = simulation.step_internal(time);
        assert_eq!(finished, false);
        assert_eq!(
            res.0,
            START_VALUE + INITIAL_VELOCITY * duration.as_secs_f32()
                - INITIAL_VELOCITY.signum() * 0.5 * DECELERATION * duration.as_secs_f32().powi(2)
        );

        duration = Duration::from_hours(10);
        assert!(Duration::from_secs((INITIAL_VELOCITY / DECELERATION) as u64) < duration);
        time += duration;
        let (res, finished) = simulation.step_internal(time);
        assert_eq!(finished, true);
        assert_eq!(
            res.0,
            START_VALUE + INITIAL_VELOCITY * f32::abs(INITIAL_VELOCITY / DECELERATION)
                - 0.5
                    * INITIAL_VELOCITY.signum()
                    * DECELERATION
                    * (INITIAL_VELOCITY / DECELERATION).powi(2)
        );

        assert!(res.0 > LIMIT_VALUE); // We reached velocity zero before we reached the position limit
    }

    /// We reach the position limit before the velocity got zero
    /// start_value > limit_value
    #[test]
    fn constant_deceleration_decreasing_limit_reached() {
        const START_VALUE: f32 = 20.;
        const LIMIT_VALUE: f32 = 10.;
        const INITIAL_VELOCITY: f32 = -50.;
        const DECELERATION: f32 = 20.;
        let parameters = ConstantDecelerationParameters::<LogicalPx> {
            initial_velocity: Length::new(INITIAL_VELOCITY),
            deceleration: Scale::new(DECELERATION),
        };

        let mut time = Instant::now();
        let mut simulation = ConstantDeceleration::new_internal(
            Length::new(START_VALUE),
            Length::new(LIMIT_VALUE),
            parameters.initial_velocity,
            parameters,
            time.clone(),
        );

        let duration = Duration::from_secs(3);
        assert!(f32::abs(DECELERATION * duration.as_secs_f32()) > f32::abs(INITIAL_VELOCITY)); // We don't reach the limit where the velocity gets zero
        time += duration;
        let (res, finished) = simulation.step_internal(time);
        assert_eq!(finished, true);
        assert_eq!(res.0, LIMIT_VALUE); // Limit reached
    }
}
        time += duration;
        let (res, finished) = simulation.step_internal(time);
        assert_eq!(finished, true);
        assert_eq!(res.0, limit_value); // Limit reached
    }
}
