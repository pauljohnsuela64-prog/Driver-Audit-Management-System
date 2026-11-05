package com.bhli.audit.mobile;

import androidx.test.rule.ActivityTestRule;
import dev.flutter.plugins.integration_test.FlutterTestRunner;
import org.junit.Rule;
import org.junit.runner.RunWith;

/** Uses native instrumentation, not a networked Flutter VM-service driver. */
@RunWith(FlutterTestRunner.class)
public class OfflineAcceptanceTest {
    @Rule
    public ActivityTestRule<MainActivity> rule =
        new ActivityTestRule<>(MainActivity.class, true, false);
}
