// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

// cSpell:ignore androidscrollcomparison Spannable tbstart tbend

import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;
import java.util.Locale;
import dev.slint.aosp.AospOverScroller;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import android.view.ActionMode;
import android.view.Menu;
import android.view.MenuItem;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewTreeObserver;
import android.view.WindowInsets;
import android.view.WindowInsetsAnimation;
import android.view.WindowMetrics;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.res.Configuration;
import android.content.res.TypedArray;
import android.graphics.BlendMode;
import android.graphics.BlendModeColorFilter;
import android.graphics.Insets;
import android.graphics.PorterDuff;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.ColorDrawable;
import android.text.Editable;
import android.text.Selection;
import android.text.SpannableStringBuilder;
import android.util.TypedValue;
import android.view.inputmethod.InputMethodManager;
import android.app.Activity;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.PopupWindow;
import android.widget.ScrollView;
import android.widget.TextView;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.SystemClock;
import android.util.Log;
import android.view.Choreographer;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.inputmethod.BaseInputConnection;
import android.os.Build;
import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;

class InputHandle extends ImageView {
    private PopupWindow mPopupWindow;
    private float mPressedX;
    private float mPressedY;
    private SlintInputView mRootView;
    private int cursorX;
    private int cursorY;
    private int attr;

    public InputHandle(SlintInputView rootView, int attr) {
        super(rootView.getContext());
        this.attr = attr;
        mRootView = rootView;
        Context ctx = rootView.getContext();
        mPopupWindow = new PopupWindow(ctx, null, android.R.attr.textSelectHandleWindowStyle);
        mPopupWindow.setSplitTouchEnabled(true);
        mPopupWindow.setClippingEnabled(false);
        int[] attrs = { attr };
        Drawable drawable = ctx.getTheme().obtainStyledAttributes(attrs).getDrawable(0);
        mPopupWindow.setWidth(drawable.getIntrinsicWidth());
        mPopupWindow.setHeight(drawable.getIntrinsicHeight());
        this.setImageDrawable(drawable);
        mPopupWindow.setContentView(this);
    }

    @Override
    public boolean onTouchEvent(MotionEvent ev) {
        switch (ev.getActionMasked()) {
            case MotionEvent.ACTION_DOWN: {
                mPressedX = ev.getRawX() - cursorX;
                mPressedY = ev.getRawY() - cursorY;
                break;
            }

            case MotionEvent.ACTION_MOVE: {
                mRootView.hideActionMenu(ActionMode.DEFAULT_HIDE_DURATION);
                int id = attr == android.R.attr.textSelectHandleLeft ? 1
                        : attr == android.R.attr.textSelectHandleRight ? 2 : 0;
                SlintAndroidJavaHelper.moveCursorHandle(id, Math.round(ev.getRawX() - mPressedX),
                        Math.round(ev.getRawY() - mPressedY));
                break;
            }
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                break;
        }
        return true;
    }

    public void setPosition(int x, int y) {
        cursorX = x;
        cursorY = y;

        if (attr == android.R.attr.textSelectHandleLeft) {
            x -= 3 * mPopupWindow.getWidth() / 4;
        } else if (attr == android.R.attr.textSelectHandleRight) {
            x -= mPopupWindow.getWidth() / 4;
        } else {
            x -= mPopupWindow.getWidth() / 2;
        }

        mPopupWindow.showAtLocation(mRootView, 0, x, y);
        mPopupWindow.update(x, y, -1, -1);
    }

    public void hide() {
        mPopupWindow.dismiss();
    }

    public void setHandleColor(int color) {
        Drawable drawable = getDrawable();
        if (drawable != null) {
            if (android.os.Build.VERSION.SDK_INT >= 29) {
                drawable.setColorFilter(new BlendModeColorFilter(color, BlendMode.SRC_IN));
            } else {
                drawable.setColorFilter(color, PorterDuff.Mode.SRC_IN);
            }
            setImageDrawable(drawable);
        }
    }
}

class SlintInputView extends View {
    private String mText = "";
    private int mCursorPosition = 0;
    private int mAnchorPosition = 0;
    private int mPreeditStart = 0;
    private int mPreeditEnd = 0;
    private int mInputType = EditorInfo.TYPE_CLASS_TEXT;
    private int mInBatch = 0;
    private boolean mPending = false;
    private SlintEditable mEditable;

    public class SlintEditable extends SpannableStringBuilder {
        public SlintEditable() {
            super(mText);
        }

        @Override
        public SpannableStringBuilder replace(int start, int end, CharSequence tb, int tbstart, int tbend) {
            super.replace(start, end, tb, tbstart, tbend);
            setCursorPos(0, 0, 0, 0, 0, 0);
            if (mInBatch == 0) {
                update();
            } else {
                mPending = true;
            }
            return this;
        }

        public void update() {
            mPending = false;
            mText = toString();
            mCursorPosition = Selection.getSelectionStart(this);
            mAnchorPosition = Selection.getSelectionEnd(this);
            mPreeditStart = BaseInputConnection.getComposingSpanStart(this);
            mPreeditEnd = BaseInputConnection.getComposingSpanEnd(this);
            SlintAndroidJavaHelper.updateText(mText, mCursorPosition, mAnchorPosition, mPreeditStart, mPreeditEnd);
        }
    }

    public SlintInputView(Context context) {
        super(context);
        setFocusable(true);
        setFocusableInTouchMode(true);
        mEditable = new SlintEditable();
    }

    @Override
    public boolean onCheckIsTextEditor() {
        return true;
    }

    @Override
    public InputConnection onCreateInputConnection(EditorInfo outAttrs) {
        outAttrs.inputType = mInputType;
        outAttrs.imeOptions = EditorInfo.IME_FLAG_NO_EXTRACT_UI;
        outAttrs.initialSelStart = mCursorPosition;
        outAttrs.initialSelEnd = mAnchorPosition;
        return new BaseInputConnection(this, true) {
            @Override
            public Editable getEditable() {
                return mEditable;
            }

            @Override
            public boolean beginBatchEdit() {
                mInBatch += 1;
                return super.beginBatchEdit();
            }

            @Override
            public boolean endBatchEdit() {
                mInBatch -= 1;
                if (mInBatch == 0 && mPending) {
                    mEditable.update();
                }
                return super.endBatchEdit();
            }
        };
    }

    public void setText(String text, int cursorPosition, int anchorPosition, int preeditStart, int preeditEnd,
            int inputType) {
        boolean typeChanged = mInputType != inputType;
        boolean textChanged = !mText.equals(text);
        boolean selectionChanged = mCursorPosition != cursorPosition || mAnchorPosition != anchorPosition;

        mText = text;
        mCursorPosition = cursorPosition;
        mAnchorPosition = anchorPosition;
        mPreeditStart = preeditStart;
        mPreeditEnd = preeditEnd;
        mInputType = inputType;

        if (typeChanged) {
            mEditable = new SlintEditable();
            Selection.setSelection(mEditable, cursorPosition, anchorPosition);
            InputMethodManager imm = (InputMethodManager) this.getContext()
                    .getSystemService(Context.INPUT_METHOD_SERVICE);
            imm.restartInput(this);
        } else if (textChanged || selectionChanged) {
            InputMethodManager imm = (InputMethodManager) this.getContext()
                    .getSystemService(Context.INPUT_METHOD_SERVICE);
            mInBatch += 1;
            try {
                if (textChanged) {
                    mEditable.replace(0, mEditable.length(), text);
                }
                if (Selection.getSelectionStart(mEditable) != cursorPosition
                        || Selection.getSelectionEnd(mEditable) != anchorPosition) {
                    Selection.setSelection(mEditable, cursorPosition, anchorPosition);
                }
            } finally {
                mInBatch -= 1;
                mPending = false;
            }
            imm.updateSelection(this, cursorPosition, anchorPosition, preeditStart, preeditEnd);
        }
    }

    @Override
    protected void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        int currentNightMode = newConfig.uiMode & Configuration.UI_MODE_NIGHT_MASK;
        SlintAndroidJavaHelper.setNightMode(currentNightMode);
        SlintAndroidJavaHelper.setFontScale(newConfig.fontScale);
    }

    private InputHandle mCursorHandle;
    private InputHandle mLeftHandle;
    private InputHandle mRightHandle;
    public Rect selectionRect = new Rect();

    // num_handles: 0=hidden, 1=cursor handle, 2=selection handles
    public void setCursorPos(int left_x, int left_y, int right_x, int right_y, int cursor_height, int num_handles) {
        int handleHeight = 0;
        if (num_handles == 1) {
            if (mLeftHandle != null) {
                mLeftHandle.hide();
            }
            if (mRightHandle != null) {
                mRightHandle.hide();
            }
            if (left_x != -1) {
                if (mCursorHandle == null) {
                    mCursorHandle = new InputHandle(this, android.R.attr.textSelectHandle);
                }
                mCursorHandle.setPosition(left_x, left_y);
                handleHeight = mCursorHandle.getHeight();
            } else if (mCursorHandle != null) {
                mCursorHandle.hide();
            }
        } else if (num_handles == 2) {
            if (left_x != -1) {
                if (mLeftHandle == null) {
                    mLeftHandle = new InputHandle(this, android.R.attr.textSelectHandleLeft);
                }
                mLeftHandle.setPosition(left_x, left_y);
                handleHeight = mLeftHandle.getHeight();
            } else {
                if (mLeftHandle != null) {
                    mLeftHandle.hide();
                }
            }
            if (right_x != -1) {
                if (mRightHandle == null) {
                    mRightHandle = new InputHandle(this, android.R.attr.textSelectHandleRight);
                }
                mRightHandle.setPosition(right_x, right_y);
                handleHeight = mRightHandle.getHeight();
            } else {
                if (mRightHandle != null) {
                    mRightHandle.hide();
                }
            }
            if (mCursorHandle != null) {
                mCursorHandle.hide();
            }
            showActionMenu();
        } else {
            if (mCursorHandle != null) {
                handleHeight = mCursorHandle.getHeight();
                mCursorHandle.hide();
            }
            if (mLeftHandle != null) {
                mLeftHandle.hide();
            }
            if (mRightHandle != null) {
                mRightHandle.hide();
            }
            hideActionMenu(-1);
        }

        selectionRect.set(Math.min(left_x, right_x), Math.min(left_y, right_y) - cursor_height,
                Math.max(left_x, right_x), Math.max(left_y, right_y) + handleHeight);
        if (mCurrentActionMode != null) {
            mCurrentActionMode.invalidateContentRect();
        }
    }

    public void setHandleColor(int color) {
        if (mCursorHandle != null) {
            mCursorHandle.setHandleColor(color);
        }
        if (mLeftHandle != null) {
            mLeftHandle.setHandleColor(color);
        }
        if (mRightHandle != null) {
            mRightHandle.setHandleColor(color);
        }
    }

    private ActionMode mCurrentActionMode;

    public void showActionMenu() {
        if (mCurrentActionMode != null) {
            mCurrentActionMode.hide(0);
            return;
        }
        ActionMode.Callback2 action = new ActionMode.Callback2() {
            @Override
            public boolean onCreateActionMode(ActionMode mode, Menu menu) {
                mode.setTitle(null);
                mode.setSubtitle(null);
                mode.setTitleOptionalHint(true);
                if (android.os.Build.VERSION.SDK_INT >= 28) {
                    menu.setGroupDividerEnabled(true);
                }

                final TypedArray a = getContext().obtainStyledAttributes(new int[] {
                        android.R.attr.actionModeCutDrawable,
                        android.R.attr.actionModeCopyDrawable,
                        android.R.attr.actionModePasteDrawable,
                        android.R.attr.actionModeSelectAllDrawable,
                });

                // Note: the ids are used in Java_SlintAndroidJavaHelper_popupMenuAction
                menu.add(Menu.FIRST, 0, 0, android.R.string.cut)
                        .setAlphabeticShortcut('x')
                        .setIcon(a.getDrawable(0));
                menu.add(Menu.FIRST, 1, 1, android.R.string.copy)
                        .setAlphabeticShortcut('c')
                        .setIcon(a.getDrawable(1));
                menu.add(Menu.FIRST, 2, 2, android.R.string.paste)
                        .setAlphabeticShortcut('v')
                        .setIcon(a.getDrawable(2));
                menu.add(Menu.FIRST, 3, 3, android.R.string.selectAll)
                        .setAlphabeticShortcut('a')
                        .setIcon(a.getDrawable(3));

                a.recycle();

                return true;
            }

            @Override
            public boolean onPrepareActionMode(ActionMode mode, Menu menu) {
                return true;
            }

            @Override
            public boolean onActionItemClicked(ActionMode mode, MenuItem item) {
                SlintAndroidJavaHelper.popupMenuAction(item.getItemId());
                mode.finish();
                return true;
            }

            @Override
            public void onDestroyActionMode(ActionMode action) {
            }

            // Introduced in API level 23
            @Override
            public void onGetContentRect(ActionMode mode, View view, Rect outRect) {
                outRect.set(selectionRect);
                if (outRect.top < 0) {
                    // FIXME: I don't know why this is the case, but without that, the menu doesn't
                    // show at the right position when there is no room on top.
                    // Looks like the menu is always shown at outRect.top.
                    outRect.top = outRect.bottom;
                }
            }

        };
        mCurrentActionMode = startActionMode(action, ActionMode.TYPE_FLOATING);

    }

    public void hideActionMenu(int duration) {
        if (mCurrentActionMode != null) {
            if (duration < 0) {
                mCurrentActionMode.finish();
                mCurrentActionMode = null;
            } else {
                mCurrentActionMode.hide(duration);
            }
        }
    }
}

class ScrollTrace {
    static int tailMillis = 15000;
    private static BufferedWriter writer;
    private static long lastFlush;
    static volatile int gesture;

    static synchronized void open(Context context) {
        if (writer != null) return;
        try {
            File directory = new File(context.getExternalFilesDir(null), "scroll-traces");
            directory.mkdirs();
            File file = new File(directory, "manual-" + System.currentTimeMillis() + ".csv");
            writer = new BufferedWriter(new FileWriter(file), 65536);
            writer.write("kind,gesture,time_ns,frame_time_ns,event_time_ms,pointer_id,action,x_px,y_px,aosp_y_dp,slint_y_dp,aosp_velocity_px_s,aosp_finished,history_count\n");
            writer.flush();
            Log.i("ScrollCompare", "TRACE_FILE," + file.getAbsolutePath());
        } catch (IOException error) {
            throw new IllegalStateException("Cannot open scroll recording", error);
        }
    }

    static synchronized void row(String row) {
        if (writer == null) return;
        try {
            writer.write(row);
            writer.newLine();
            long now = SystemClock.uptimeMillis();
            if (now - lastFlush >= 1000) {
                writer.flush();
                lastFlush = now;
            }
        } catch (IOException error) {
            Log.e("ScrollCompare", "Cannot write scroll recording", error);
        }
    }

    static void slint(float offset) {
        row("slint_sample," + gesture + "," + System.nanoTime()
                + ",,,,,,,," + offset + ",,,");
    }
}

class ScrollComparisonView extends ScrollView implements Choreographer.FrameCallback {
    private final float density;
    private final String traceId;
    private final AospOverScroller aospScroller;
    private ScrollComparisonView mirror;
    private View eventTarget;
    private TextView metricsLabel;
    private android.view.VelocityTracker velocityTracker;
    private boolean recording;
    long recordUntilMillis;
    private int phase = -1;
    private long previousFrameTimeNanos;
    private float previousNativeOffset;
    private float previousSlintOffset;
    private float maxOffsetDifference;
    private long lastMetricsUpdate;

    ScrollComparisonView(Context context, String traceId, boolean overlay) {
        super(context);
        this.traceId = traceId;
        ScrollTrace.open(context);
        aospScroller = new AospOverScroller(context);
        density = context.getResources().getDisplayMetrics().density;
        setBackgroundColor(overlay ? Color.TRANSPARENT : Color.rgb(244, 246, 250));
        setFillViewport(true);
        setOverScrollMode(View.OVER_SCROLL_NEVER);
        setVerticalScrollBarEnabled(false);

        LinearLayout rows = new LinearLayout(context);
        rows.setOrientation(LinearLayout.VERTICAL);
        for (int row = 0; row < 1000; row++) {
            TextView label = new TextView(context);
            label.setText((overlay ? "AOSP " : "Row ") + (row + 1));
            label.setTextSize(18);
            label.setIncludeFontPadding(false);
            label.setTextColor(overlay ? Color.rgb(184, 20, 10) : Color.rgb(23, 35, 59));
            label.setGravity(Gravity.CENTER_VERTICAL | (overlay ? Gravity.RIGHT : Gravity.LEFT));
            label.setPadding(dp(12), 0, dp(12), 0);
            label.setBackgroundColor(overlay
                    ? (row % 2 == 0 ? Color.argb(52, 255, 46, 31) : Color.argb(16, 255, 255, 255))
                    : (row % 2 == 0 ? Color.rgb(228, 235, 245) : Color.WHITE));
            rows.addView(label, new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    Math.round((row + 1) * 56 * density) - Math.round(row * 56 * density)));
        }
        addView(rows, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));
    }

    @Override
    public void fling(int velocityY) {
        int maximum = Math.max(0, getChildAt(0).getHeight()
                - (getHeight() - getPaddingTop() - getPaddingBottom()));
        aospScroller.fling(0, getScrollY(), 0, velocityY, 0, 0, 0, maximum);
        ScrollTrace.row("fling," + ScrollTrace.gesture + "," + System.nanoTime()
                + ",,,,,,," + (getScrollY() / density) + ",," + velocityY + ",false,0");
        Log.i("ScrollCompare", "AOSP_FLING," + velocityY + ","
                + getScrollY() + "," + aospScroller.getFinalY());
        postInvalidateOnAnimation();
    }

    @Override
    public void computeScroll() {
        if (aospScroller != null && aospScroller.computeScrollOffset()) {
            scrollTo(0, aospScroller.getCurrY());
            postInvalidateOnAnimation();
        }
    }

    @Override
    protected void onScrollChanged(int x, int y, int oldX, int oldY) {
        super.onScrollChanged(x, y, oldX, oldY);
        ScrollTrace.row("aosp_offset," + ScrollTrace.gesture + "," + System.nanoTime()
                + ",,,,,,," + (y / density) + ",,,,");
    }

    private int dp(int value) {
        return Math.round(value * density);
    }

    void setMirror(ScrollComparisonView mirror) {
        this.mirror = mirror;
    }

    void setEventTarget(View eventTarget) {
        this.eventTarget = eventTarget;
    }

    void setMetricsLabel(TextView metricsLabel) {
        this.metricsLabel = metricsLabel;
    }

    void startRecording() {
        if (recording) return;
        recording = true;
        Choreographer.getInstance().postFrameCallback(this);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            aospScroller.forceFinished(true);
            ScrollTrace.gesture++;
        }
        for (int pointer = 0; pointer < event.getPointerCount(); pointer++) {
            for (int history = 0; history < event.getHistorySize(); history++) {
                ScrollTrace.row("touch_history," + ScrollTrace.gesture + "," + System.nanoTime()
                        + ",," + event.getHistoricalEventTime(history) + "," + event.getPointerId(pointer)
                        + "," + event.getActionMasked() + "," + event.getHistoricalX(pointer, history)
                        + "," + event.getHistoricalY(pointer, history) + ",,,,," + event.getHistorySize());
            }
            ScrollTrace.row("touch," + ScrollTrace.gesture + "," + System.nanoTime()
                    + ",," + event.getEventTime() + "," + event.getPointerId(pointer)
                    + "," + event.getActionMasked() + "," + event.getX(pointer)
                    + "," + event.getY(pointer) + ",,,,," + event.getHistorySize());
        }
        if (mirror != null) {
            MotionEvent copiedEvent = MotionEvent.obtain(event);
            mirror.onTouchEvent(copiedEvent);
            copiedEvent.recycle();
        }
        if (eventTarget != null) {
            MotionEvent copiedEvent = MotionEvent.obtain(event);
            int[] sourceLocation = new int[2];
            int[] targetLocation = new int[2];
            getLocationOnScreen(sourceLocation);
            eventTarget.getLocationOnScreen(targetLocation);
            copiedEvent.offsetLocation(
                    sourceLocation[0] - targetLocation[0],
                    sourceLocation[1] - targetLocation[1]);
            SlintAndroidJavaHelper.forwardTouch(copiedEvent);
            copiedEvent.recycle();
        }
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                velocityTracker = android.view.VelocityTracker.obtain();
                velocityTracker.addMovement(event);
                phase = 0;
                previousFrameTimeNanos = 0;
                previousNativeOffset = getScrollY() / density;
                previousSlintOffset = SlintAndroidJavaHelper.slintScrollOffset();
                maxOffsetDifference = Math.abs(previousSlintOffset - previousNativeOffset);
                recordUntilMillis = Long.MAX_VALUE;
                startRecording();
                break;
            case MotionEvent.ACTION_MOVE:
                velocityTracker.addMovement(event);
                phase = 1;
                break;
            case MotionEvent.ACTION_UP:
                velocityTracker.addMovement(event);
                velocityTracker.computeCurrentVelocity(1000);
                Log.i("ScrollCompare", "V," + traceId + ","
                        + (velocityTracker.getYVelocity() / density));
                velocityTracker.recycle();
                velocityTracker = null;
                phase = 2;
                recordUntilMillis = SystemClock.uptimeMillis() + ScrollTrace.tailMillis;
                break;
            case MotionEvent.ACTION_CANCEL:
                if (velocityTracker != null) {
                    velocityTracker.recycle();
                    velocityTracker = null;
                }
                phase = 3;
                recordUntilMillis = SystemClock.uptimeMillis() + ScrollTrace.tailMillis;
                break;
        }
        return super.onTouchEvent(event);
    }

    @Override
    public void doFrame(long frameTimeNanos) {
        float nativeOffset = getScrollY() / density;
        float slintOffset = SlintAndroidJavaHelper.slintScrollOffset();
        float difference = slintOffset - nativeOffset;
        maxOffsetDifference = Math.max(maxOffsetDifference, Math.abs(difference));
        float frameSeconds = previousFrameTimeNanos == 0
                ? 0 : (frameTimeNanos - previousFrameTimeNanos) / 1_000_000_000.0f;
        float nativeVelocity = frameSeconds == 0
                ? 0 : (nativeOffset - previousNativeOffset) / frameSeconds;
        float slintVelocity = frameSeconds == 0
                ? 0 : (slintOffset - previousSlintOffset) / frameSeconds;
        ScrollTrace.row("frame," + ScrollTrace.gesture + "," + System.nanoTime() + ","
                + frameTimeNanos + ",,," + phase + ",,," + nativeOffset + "," + slintOffset
                + "," + aospScroller.getCurrVelocity() + "," + aospScroller.isFinished() + ",0");
        if (metricsLabel != null && frameTimeNanos - lastMetricsUpdate >= 100_000_000L) {
            lastMetricsUpdate = frameTimeNanos;
            float percent = nativeOffset == 0 ? 0 : difference / Math.abs(nativeOffset) * 100;
            metricsLabel.setText(String.format(Locale.US,
                    "OFFSET   AOSP    %7.1f  Slint %7.1f\n"
                            + "DIFFERENCE       %+7.1f  (%+6.1f%%)\n"
                            + "VELOCITY AOSP    %7.0f  Slint %7.0f\n"
                            + "VELOCITY Δ       %+7.0f\n"
                            + "MAX OFFSET Δ      %7.1f   REC",
                    nativeOffset, slintOffset, difference, percent,
                    nativeVelocity, slintVelocity, slintVelocity - nativeVelocity,
                    maxOffsetDifference));
        }
        previousFrameTimeNanos = frameTimeNanos;
        previousNativeOffset = nativeOffset;
        previousSlintOffset = slintOffset;
        if (recordUntilMillis == Long.MAX_VALUE || SystemClock.uptimeMillis() < recordUntilMillis) {
            Choreographer.getInstance().postFrameCallback(this);
        } else {
            recording = false;
        }
    }
}

public class SlintAndroidJavaHelper {
    Activity mActivity;
    SlintInputView mInputView;
    PopupWindow mComparisonPopup;
    PopupWindow mControlPopup;
    private OnBackInvokedCallback mBackCallback;

    public SlintAndroidJavaHelper(Activity activity) {
        this.mActivity = activity;
        ScrollTrace.tailMillis = activity.getIntent().getIntExtra("recording_tail_ms", 15000);
        this.mInputView = new SlintInputView(activity);
        this.mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT);
                mActivity.addContentView(mInputView, params);
                mInputView.setVisibility(View.VISIBLE);

                if ("dev.slint.aospscrollcomparison".equals(mActivity.getPackageName())) {
                    boolean nativeControl = mActivity.getIntent().getBooleanExtra("native_control", false);
                    float density = mActivity.getResources().getDisplayMetrics().density;
                    LinearLayout nativePane = new LinearLayout(mActivity);
                nativePane.setOrientation(LinearLayout.VERTICAL);
                nativePane.setBackgroundColor(nativeControl
                        ? Color.rgb(244, 246, 250) : Color.TRANSPARENT);
                LinearLayout titleRow = new LinearLayout(mActivity);
                titleRow.setOrientation(LinearLayout.HORIZONTAL);
                titleRow.setBackgroundColor(Color.argb(245, 255, 255, 255));
                TextView slintTitle = new TextView(mActivity);
                slintTitle.setText(nativeControl ? "AOSP A" : "Slint Murmele");
                slintTitle.setTextSize(18);
                slintTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
                slintTitle.setTextColor(nativeControl
                        ? Color.rgb(23, 35, 59) : Color.rgb(20, 90, 170));
                slintTitle.setGravity(Gravity.CENTER);
                titleRow.addView(slintTitle, new LinearLayout.LayoutParams(
                        0, LinearLayout.LayoutParams.MATCH_PARENT, nativeControl ? 1 : 0.5f));
                if (!nativeControl) {
                    TextView androidTitle = new TextView(mActivity);
                    androidTitle.setText("AOSP");
                    androidTitle.setTextSize(18);
                    androidTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
                    androidTitle.setTextColor(Color.rgb(184, 20, 10));
                    androidTitle.setGravity(Gravity.CENTER);
                    titleRow.addView(androidTitle, new LinearLayout.LayoutParams(
                            0, LinearLayout.LayoutParams.MATCH_PARENT, 0.5f));
                }
                nativePane.addView(titleRow, new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        Math.round(48 * density)));
                FrameLayout comparisonContent = new FrameLayout(mActivity);
                ScrollComparisonView nativeList =
                        new ScrollComparisonView(mActivity, "A", !nativeControl);
                slintTitle.setOnClickListener(view -> {
                    if (nativeList.getScrollY() == 0) {
                        nativeList.post(() -> nativeList.fullScroll(View.FOCUS_DOWN));
                    } else {
                        nativeList.fullScroll(View.FOCUS_UP);
                    }
                });
                comparisonContent.addView(nativeList, new FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT));
                if (!nativeControl) {
                    nativeList.setEventTarget(mInputView);
                    nativeList.post(() -> {
                        nativeList.scrollTo(0, Math.round(99 * 56 * density));
                        nativeList.recordUntilMillis = SystemClock.uptimeMillis() + ScrollTrace.tailMillis;
                        nativeList.startRecording();
                    });
                    TextView metrics = new TextView(mActivity);
                    metrics.setTextSize(11);
                    metrics.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
                    metrics.setTextColor(Color.WHITE);
                    metrics.setBackgroundColor(Color.argb(220, 15, 15, 15));
                    metrics.setPadding(Math.round(12 * density), Math.round(8 * density),
                            Math.round(12 * density), Math.round(8 * density));
                    metrics.setText("OFFSET   AOSP        0.0  Slint     0.0\n"
                            + "DIFFERENCE          +0.0  ( +0.0%)\n"
                            + "VELOCITY AOSP          0  Slint       0\n"
                            + "VELOCITY Δ             +0\n"
                            + "MAX OFFSET Δ          0.0");
                    FrameLayout.LayoutParams metricsParams = new FrameLayout.LayoutParams(
                            Math.round(340 * density), FrameLayout.LayoutParams.WRAP_CONTENT,
                            Gravity.TOP | Gravity.RIGHT);
                    metricsParams.setMargins(0, Math.round(8 * density), Math.round(8 * density), 0);
                    comparisonContent.addView(metrics, metricsParams);
                    nativeList.setMetricsLabel(metrics);
                }
                nativePane.addView(comparisonContent,
                        new LinearLayout.LayoutParams(
                                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));
                mComparisonPopup = new PopupWindow(
                        nativePane,
                        nativeControl
                                ? mActivity.getResources().getDisplayMetrics().widthPixels / 2
                                : FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        false);
                mComparisonPopup.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
                mComparisonPopup.setTouchable(true);
                mComparisonPopup.setOutsideTouchable(false);
                mComparisonPopup.setClippingEnabled(false);
                mInputView.post(() -> mComparisonPopup.showAtLocation(
                        mInputView, Gravity.LEFT | Gravity.TOP, 0, 0));

                    if (nativeControl) {
                    LinearLayout controlPane = new LinearLayout(mActivity);
                    controlPane.setOrientation(LinearLayout.VERTICAL);
                    controlPane.setBackgroundColor(Color.rgb(244, 246, 250));
                    TextView controlTitle = new TextView(mActivity);
                    controlTitle.setText("AOSP B");
                    controlTitle.setTextSize(18);
                    controlTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
                    controlTitle.setTextColor(Color.rgb(23, 35, 59));
                    controlTitle.setGravity(Gravity.CENTER);
                    controlPane.addView(controlTitle, new LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            Math.round(48 * mActivity.getResources().getDisplayMetrics().density)));
                    ScrollComparisonView controlList = new ScrollComparisonView(mActivity, "B", false);
                    controlPane.addView(controlList, new LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));
                    nativeList.setMirror(controlList);
                    mControlPopup = new PopupWindow(
                            controlPane,
                            mActivity.getResources().getDisplayMetrics().widthPixels / 2,
                            FrameLayout.LayoutParams.MATCH_PARENT,
                            false);
                    mControlPopup.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
                    mControlPopup.setTouchable(false);
                    mControlPopup.setClippingEnabled(false);
                    mInputView.post(() -> mControlPopup.showAtLocation(
                            mInputView, Gravity.RIGHT | Gravity.TOP, 0, 0));
                    }
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    mActivity.getWindow().getDecorView().getRootView()
                            .setOnApplyWindowInsetsListener((v, insets) -> dispatchInsets(insets));
                    // Attach the IME animation callback to the input view rather than the
                    // decor root: some OEM ROMs fail to render the IME surface when an
                    // animation callback is installed on the window's root view.
                    mInputView.setWindowInsetsAnimationCallback(
                            new WindowInsetsAnimation.Callback(
                                    WindowInsetsAnimation.Callback.DISPATCH_MODE_CONTINUE_ON_SUBTREE) {
                                @Override
                                public WindowInsets onProgress(WindowInsets insets,
                                        java.util.List<WindowInsetsAnimation> runningAnimations) {
                                    return dispatchInsets(insets);
                                }
                            });
                }
                // On API 34+, Back arrives via OnBackInvokedDispatcher; forward
                // it into Slint's key-event pipeline.
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE && mBackCallback == null) {
                    mBackCallback = () -> SlintAndroidJavaHelper.onBackInvoked();
                    mActivity.getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                            OnBackInvokedDispatcher.PRIORITY_DEFAULT, mBackCallback);
                }
            }
        });
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            activity.getWindow().getDecorView().getRootView().getViewTreeObserver()
                    .addOnGlobalLayoutListener(new ViewTreeObserver.OnGlobalLayoutListener() {
                        @Override
                        public void onGlobalLayout() {
                            mActivity.runOnUiThread(new Runnable() {
                                @Override
                                public void run() {
                                    Rect windowRect = get_view_rect();
                                    Rect safeAreaRect = get_safe_area();

                                    // This is only an approximation, because SDK level < 30 doesn't provide
                                    // a way to get the keyboard area directly.
                                    Rect visibleRect = new Rect();
                                    mActivity.getWindow().getDecorView().getRootView()
                                            .getWindowVisibleDisplayFrame(visibleRect);
                                    int keyboardBottom = windowRect.bottom - visibleRect.bottom;
                                    int keyboardLeft = windowRect.left - visibleRect.left;
                                    int keyboardTop = windowRect.top - visibleRect.top;
                                    int keyboardRight = windowRect.right - visibleRect.right;
                                    int max = Math.max(keyboardBottom, Math.max(keyboardLeft,
                                            Math.max(keyboardTop, keyboardRight)));

                                    // only take the largest value (it's probably always going to be bottom)
                                    if (max == keyboardBottom) {
                                        keyboardTop = 0;
                                        keyboardLeft = 0;
                                        keyboardRight = 0;
                                    } else if (max == keyboardLeft) {
                                        keyboardTop = 0;
                                        keyboardRight = 0;
                                        keyboardBottom = 0;
                                    } else if (max == keyboardTop) {
                                        keyboardLeft = 0;
                                        keyboardRight = 0;
                                        keyboardBottom = 0;
                                    } else {
                                        keyboardTop = 0;
                                        keyboardLeft = 0;
                                        keyboardBottom = 0;
                                    }

                                    SlintAndroidJavaHelper.setInsets(
                                            windowRect.top, windowRect.left,
                                            windowRect.bottom, windowRect.right,
                                            safeAreaRect.top, safeAreaRect.left,
                                            safeAreaRect.bottom, safeAreaRect.right,
                                            keyboardTop, keyboardLeft,
                                            keyboardBottom, keyboardRight);
                                }
                            });
                        }
                    });
        }
    }

    private WindowInsets dispatchInsets(WindowInsets insets) {
        // The listener-supplied `insets` reflects what reaches the decor view
        // AFTER any ancestor has consumed insets, so in edge-to-edge mode the
        // system bars and the display cutout often arrive as zero. Read those
        // straight from the WindowManager, which always returns the unconsumed
        // values — matching what get_safe_area() does. The IME inset still
        // comes from the listener stream so keyboard show/hide animates.
        Insets sysBars;
        Insets cutout;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsets src = mActivity.getWindowManager().getCurrentWindowMetrics().getWindowInsets();
            sysBars = src.getInsets(WindowInsets.Type.systemBars());
            cutout = src.getInsets(WindowInsets.Type.displayCutout());
        } else {
            sysBars = insets.getInsets(WindowInsets.Type.systemBars());
            cutout = insets.getInsets(WindowInsets.Type.displayCutout());
        }
        Insets safeAreaInsets = Insets.max(sysBars, cutout);
        Insets keyboardAreaInsets = insets.getInsets(WindowInsets.Type.ime());
        Rect windowRect = get_view_rect();
        SlintAndroidJavaHelper.setInsets(
                windowRect.top, windowRect.left,
                windowRect.bottom, windowRect.right,
                safeAreaInsets.top, safeAreaInsets.left,
                safeAreaInsets.bottom, safeAreaInsets.right,
                keyboardAreaInsets.top, keyboardAreaInsets.left,
                keyboardAreaInsets.bottom, keyboardAreaInsets.right);
        return insets;
    }

    public void show_keyboard() {
        mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                mInputView.requestFocus();
                InputMethodManager imm = (InputMethodManager) mActivity.getSystemService(Context.INPUT_METHOD_SERVICE);
                imm.showSoftInput(mInputView, 0);
            }
        });
    }

    public void hide_keyboard() {
        mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                InputMethodManager imm = (InputMethodManager) mActivity.getSystemService(Context.INPUT_METHOD_SERVICE);
                imm.hideSoftInputFromWindow(mInputView.getWindowToken(), 0);
                mInputView.clearFocus();
                mInputView.setCursorPos(0, 0, 0, 0, 0, 0);
            }
        });
    }

    // Called from Rust when an OnBackInvokedCallback fires and Slint's key
    // dispatch reports the Back key as unhandled — preserves the legacy
    // Back-closes-the-activity default.
    public void finish_activity() {
        mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                mActivity.finish();
            }
        });
    }

    static public native void updateText(String text, int cursorPosition, int anchorPosition, int preeditStart,
            int preeditOffset);

    static public native void setNightMode(int nightMode);

    static public native void setFontScale(float fontScale);

    static public native void onBackInvoked();

    static public void recordConsumedSample(int kind, int action, long eventTime,
            float x, float y, int historyCount) {
        ScrollTrace.row((kind == 0 ? "consumed_touch," : "consumed_history,")
                + ScrollTrace.gesture + "," + System.nanoTime() + ",," + eventTime
                + ",0," + action + "," + x + "," + y + ",,,,," + historyCount);
    }

    static public void recordSlintSample(float offset) { ScrollTrace.slint(offset); }

    static public native void forwardTouch(MotionEvent event);

    static public native float slintScrollOffset();

    static public native void moveCursorHandle(int id, int pos_x, int pos_y);

    static public native void popupMenuAction(int id);

    static public native void setInsets(int window_top, int window_left, int window_bottom, int window_right,
            int safe_area_top, int safe_area_left, int safe_area_bottom, int safe_area_right,
            int keyboard_top, int keyboard_left, int keyboard_bottom, int keyboard_right);

    public void set_imm_data(String text, int cursor_position, int anchor_position, int preedit_start, int preedit_end,
            int cur_x, int cur_y, int anchor_x, int anchor_y, int cursor_height, int input_type,
            boolean show_cursor_handles) {

        mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                int selStart = Math.min(cursor_position, anchor_position);
                int selEnd = Math.max(cursor_position, anchor_position);
                mInputView.setText(text, selStart, selEnd, preedit_start, preedit_end, input_type);
                int num_handles = 0;
                if (show_cursor_handles) {
                    num_handles = cursor_position == anchor_position ? 1 : 2;
                }
                if (cursor_position < anchor_position) {
                    mInputView.setCursorPos(cur_x, cur_y, anchor_x, anchor_y, cursor_height, num_handles);
                } else {
                    mInputView.setCursorPos(anchor_x, anchor_y, cur_x, cur_y, cursor_height, num_handles);
                }

            }
        });
    }

    public void set_handle_color(int color) {
        mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                mInputView.setHandleColor(color);
            }
        });
    }

    public int color_scheme() {
        int nightModeFlags = mActivity.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        return nightModeFlags;
    }

    public float font_scale() {
        return mActivity.getResources().getConfiguration().fontScale;
    }

    public int accent_color() {
        TypedValue typedValue = new TypedValue();
        if (mActivity.getTheme().resolveAttribute(android.R.attr.colorAccent, typedValue, true)) {
            return mActivity.getColor(typedValue.resourceId);
        }
        return 0;
    }

    // Get the size of the window
    public Rect get_view_rect() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // On Android 11 and above, we can get the window bounds directly
            WindowMetrics metrics = mActivity.getWindowManager().getCurrentWindowMetrics();
            return metrics.getBounds();
        } else {
            View rootView = mActivity.getWindow().getDecorView().getRootView();
            return new Rect(rootView.getLeft(), rootView.getTop(), rootView.getRight(), rootView.getBottom());
        }
    }

    // On SDK level < 30, returns the inset for the safe area and the keyboard.
    // On SDK level >= 30, returns the inset for the safe area only.
    public Rect get_safe_area() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowMetrics metrics = mActivity.getWindowManager().getCurrentWindowMetrics();
            WindowInsets insets = metrics.getWindowInsets();
            Insets safeArea = Insets.max(
                    insets.getInsets(WindowInsets.Type.systemBars()),
                    insets.getInsets(WindowInsets.Type.displayCutout()));
            return new Rect(safeArea.left, safeArea.top, safeArea.right, safeArea.bottom);
        } else {
            View decorView = mActivity.getWindow().getDecorView();
            // Note: `View.getRootWindowInsets` requires API level 23 or above
            WindowInsets insets = decorView.getRootView().getRootWindowInsets();
            if (insets != null) {
                return new Rect(
                        insets.getStableInsetLeft(),
                        insets.getStableInsetTop(),
                        insets.getStableInsetRight(),
                        insets.getStableInsetBottom());
            }
            return new Rect(0, 0, 0, 0);
        }
    }

    public void show_action_menu() {
        mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                mInputView.showActionMenu();
            }
        });
    }

    public String get_clipboard() {
        FutureTask<String> future = new FutureTask<>(new Callable<String>() {
            @Override
            public String call() throws Exception {
                ClipboardManager clipboard = (ClipboardManager) mActivity.getSystemService(Context.CLIPBOARD_SERVICE);
                if (clipboard.hasPrimaryClip()) {
                    ClipData.Item item = clipboard.getPrimaryClip().getItemAt(0);
                    return item.getText().toString();
                }
                return "";
            }
        });

        mActivity.runOnUiThread(future);
        try {
            return future.get(); // Wait for the result and return it
        } catch (Exception e) {
            e.printStackTrace();
            return "";
        }
    }

    public void set_clipboard(String text) {
        mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                ClipboardManager clipboard = (ClipboardManager) mActivity.getSystemService(Context.CLIPBOARD_SERVICE);
                ClipData clip = ClipData.newPlainText(null, text);
                clipboard.setPrimaryClip(clip);
            }
        });
    }
}
