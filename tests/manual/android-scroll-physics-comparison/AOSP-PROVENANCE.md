<!-- Copyright © SixtyFPS GmbH <info@slint.dev> -->
<!-- SPDX-License-Identifier: MIT -->

# AOSP Comparison Build

Slint base: `4e05af780806a06889f0effaad407949eb8a644d` (origin/master).
AOSP source: Android 16, frameworks/base `99b01a65cc4c104933788b3143285ab6bae65827`.

Sources retain their Apache 2.0 copyright and license headers.
OverScroller is renamed and relocated to dev.slint.aosp.
Hidden UnsupportedAppUsage annotations are removed.
The matching Scroller.ViscousFluidInterpolator is embedded because it is package-private.
Friction is fixed to AOSP's 0.015 default instead of querying the Samsung framework.
Spline coefficients and fling calculations are unchanged.

The native comparison view overrides fling and computeScroll to use the bundled class.
Samsung ScrollView touch recognition and Android VelocityTracker remain in use.
Edge effects are disabled; this is a free-fling comparison, not a complete AOSP widget port.
Slint core physics are unchanged from the recorded master revision.
