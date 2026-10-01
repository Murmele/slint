// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT

use raw_window_handle::{HasWindowHandle, RawWindowHandle};
use slint::winit_030::WinitWindowAccessor;

slint::slint! {
    import { ScrollView } from "std-widgets.slint";
    export component Comparison inherits Window {
        title: "UIKit over Slint";
        background: #f4f6fa;
        in property <int> row-count: 1000;
        out property <float> scroll-offset: -list.content-y / 1px;
        out property <float> viewport-x: (list.x + (list.width - list.visible-width) / 2) / 1px;
        out property <float> viewport-y: (list.y + (list.height - list.visible-height) / 2) / 1px;
        out property <float> viewport-width: list.visible-width / 1px;
        out property <float> viewport-height: list.visible-height / 1px;
        out property <float> content-width: list.content-width / 1px;
        out property <float> content-height: list.content-height / 1px;
        callback set-scroll-offset(float);
        callback scroll-moved();
        set-scroll-offset(offset) => { list.content-y = -offset * 1px; }
        list := ScrollView {
            x: 8px; y: 102px;
            width: root.width - 16px; height: root.height - 148px;
            content-width: self.width - 12px; content-height: root.row-count * 72px;
            horizontal-scrollbar-policy: ScrollBarPolicy.always-off;
            scrolled => { root.scroll-moved(); }
            for row in root.row-count : Rectangle {
                y: row * 72px; height: 72px; width: list.content-width;
                background: mod(row, 2) == 0 ? #e4ebf5 : #ffffff;
                Text {
                    x: 12px; height: parent.height; vertical-alignment: center;
                    text: "Slint " + (row + 1); font-size: 16px; color: #145aaa;
                }
            }
        }
    }
}

thread_local! {
    static APP: std::cell::RefCell<Option<slint::Weak<Comparison>>> = const { std::cell::RefCell::new(None) };
}

#[repr(C)]
#[derive(Default)]
struct ScrollGeometry {
    x: f32,
    y: f32,
    width: f32,
    height: f32,
    content_width: f32,
    content_height: f32,
}

#[unsafe(no_mangle)]
extern "C" fn slint_scroll_geometry() -> ScrollGeometry {
    APP.with(|slot| {
        slot.borrow().as_ref().and_then(slint::Weak::upgrade).map_or_else(
            ScrollGeometry::default,
            |app| ScrollGeometry {
                x: app.get_viewport_x(),
                y: app.get_viewport_y(),
                width: app.get_viewport_width(),
                height: app.get_viewport_height(),
                content_width: app.get_content_width(),
                content_height: app.get_content_height(),
            },
        )
    })
}

#[unsafe(no_mangle)]
extern "C" fn slint_scroll_offset() -> f32 {
    APP.with(|slot| {
        slot.borrow()
            .as_ref()
            .and_then(slint::Weak::upgrade)
            .map_or(0.0, |app| app.get_scroll_offset())
    })
}

#[unsafe(no_mangle)]
extern "C" fn slint_animation_clock_lag_ms() -> f32 {
    APP.with(|slot| {
        slot.borrow().as_ref().and_then(slint::Weak::upgrade).map_or(0.0, |app| {
            let ctx = i_slint_core::window::WindowInner::from_pub(app.window()).context();
            let now = i_slint_core::animations::Instant::now(ctx).as_nanos();
            let tick = i_slint_core::animations::current_tick().as_nanos();
            (now as f64 - tick as f64) as f32 / 1_000_000.
        })
    })
}

#[repr(C)]
struct TouchSample {
    timestamp: f64,
    x: f32,
    y: f32,
}

// Diagnostic path: preserve the UIKit samples that Winit currently discards.
#[unsafe(no_mangle)]
unsafe extern "C" fn slint_diagnostic_touch(
    id: i32,
    phase: i32,
    x: f32,
    y: f32,
    timestamp: f64,
    callback_time: f64,
    samples: *const TouchSample,
    sample_count: usize,
) {
    use i_slint_core::{
        animations::Instant,
        input::{TouchHistory, TouchPhase},
        lengths::LogicalPoint,
        platform::{InternalEvent, WindowEvent},
    };
    APP.with(|slot| {
        if let Some(app) = slot.borrow().as_ref().and_then(slint::Weak::upgrade) {
            let ctx = i_slint_core::window::WindowInner::from_pub(app.window()).context();
            ctx.update_timers_and_animations();
            let now = Instant::now(ctx);
            let sample_time = |time: f64| {
                now - std::time::Duration::from_secs_f64((callback_time - time).max(0.))
            };
            // The caller owns this array and keeps it alive throughout the synchronous call.
            let samples = unsafe { std::slice::from_raw_parts(samples, sample_count) };
            let history = TouchHistory {
                history: samples
                    .iter()
                    .filter(|sample| sample.timestamp < timestamp)
                    .map(|sample| {
                        (LogicalPoint::new(sample.x, sample.y), sample_time(sample.timestamp))
                    })
                    .collect(),
            };
            let phase = match phase {
                0 => TouchPhase::Started,
                1 => TouchPhase::Moved,
                2 => TouchPhase::Ended,
                _ => TouchPhase::Cancelled,
            };
            app.window().dispatch_event(WindowEvent::internal(InternalEvent::Touch {
                id,
                position: LogicalPoint::new(x, y),
                phase,
                event_time: Some(sample_time(timestamp)),
                history,
            }));
        }
    });
}

#[unsafe(no_mangle)]
extern "C" fn set_slint_scroll_offset(offset: f32) {
    APP.with(|slot| {
        if let Some(app) = slot.borrow().as_ref().and_then(slint::Weak::upgrade) {
            app.invoke_set_scroll_offset(offset);
        }
    });
}

unsafe extern "C" {
    fn install_native_scroll(host: *mut std::ffi::c_void);
    fn record_slint_drag();
}

fn main() {
    let app = Comparison::new().unwrap();
    let rows = std::env::var("SCROLL_ROW_COUNT")
        .ok()
        .and_then(|value| value.parse::<i32>().ok())
        .filter(|count| (1..=1000).contains(count))
        .unwrap_or(1000);
    app.set_row_count(rows);
    APP.with(|slot| *slot.borrow_mut() = Some(app.as_weak()));
    app.on_scroll_moved(|| unsafe { record_slint_drag() });
    let weak = app.as_weak();
    slint::spawn_local(async move {
        let app = weak.unwrap();
        let window = app.window().winit_window().await.unwrap();
        let RawWindowHandle::UiKit(handle) = window.window_handle().unwrap().as_raw() else {
            panic!("This comparison requires iOS");
        };
        unsafe { install_native_scroll(handle.ui_view.as_ptr()) };
    })
    .unwrap();
    app.run().unwrap();
}
