// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT
// cspell:ignore fobjc

fn main() {
    cc::Build::new()
        .files(["native_scroll.m", "hid_trace.m"])
        .flag("-fobjc-arc")
        .compile("native_scroll");
    println!("cargo:rustc-link-lib=framework=UIKit");
    println!("cargo:rerun-if-changed=native_scroll.m");
    println!("cargo:rerun-if-changed=hid_trace.m");
}
