// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0
use super::fling::weighted_recent_velocity;
use super::ring_buffer::VelocityRingBuffer;
use super::{VelocityEstimate, VelocityEstimator, VelocityTracker};
use crate::animations::Instant;
use crate::lengths::LogicalVector;

#[derive(Default, Debug)]
pub(crate) struct LegacyVelocityTracker {
    buffer: VelocityRingBuffer<4>,
}

impl VelocityTracker for LegacyVelocityTracker {
    fn push(&mut self, time: Instant, delta: LogicalVector) {
        self.buffer.push(time, delta);
    }
    fn last_time(&self) -> Option<Instant> {
        self.buffer.last_time()
    }
}
impl VelocityEstimator for LegacyVelocityTracker {
    fn estimate_velocity_internal(&self) -> Option<VelocityEstimate> {
        Some(VelocityEstimate {
            velocity: weighted_recent_velocity(&self.buffer, [0.6, 0.35, 0.05]),
            confidence: 1.,
        })
    }
}
