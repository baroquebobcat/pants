// Copyright 2017 Pants project contributors (see CONTRIBUTORS.md).
// Licensed under the Apache License, Version 2.0 (see LICENSE).

package org.pantsbuild.tools.junit.impl;

import com.google.common.base.Charsets;
import com.google.common.collect.Lists;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.PrintStream;
import java.io.UnsupportedEncodingException;
import java.util.List;
import org.junit.After;
import org.junit.Before;
import org.junit.Ignore;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.junit.runner.Result;
import org.junit.runner.notification.RunListener;
import org.junit.runner.notification.StoppedByUserException;
import org.pantsbuild.tools.junit.impl.security.JSecMgr;
import org.pantsbuild.tools.junit.impl.security.JSecMgrConfig;
import org.pantsbuild.tools.junit.lib.AllFailingTest;
import org.pantsbuild.tools.junit.lib.AllPassingTest;
import org.pantsbuild.tools.junit.lib.ExceptionInSetupTest;
import org.pantsbuild.tools.junit.lib.OutputModeTest;
import org.pantsbuild.tools.junit.lib.security.SecBoundarySystemExitTests;
import org.pantsbuild.tools.junit.lib.security.SecDanglingThreadFromTestCase;
import org.pantsbuild.tools.junit.lib.security.SecStaticSysExitTestCase;
import org.pantsbuild.tools.junit.lib.security.ThreadStartedInBeforeClassAndJoinedAfterTest;
import org.pantsbuild.tools.junit.lib.security.ThreadStartedInBeforeClassAndNotJoinedAfterTest;
import org.pantsbuild.tools.junit.lib.security.ThreadStartedInBeforeTest;

import static org.hamcrest.CoreMatchers.containsString;
import static org.hamcrest.CoreMatchers.not;
import static org.hamcrest.MatcherAssert.assertThat;
import static org.junit.Assert.fail;
import static org.pantsbuild.tools.junit.impl.security.JSecMgrConfig.*;

/**
 * These tests are similar to the tests in ConsoleRunnerTest but they create a ConosoleRunnerImpl
 * directory so they can capture the output more easily and test assertions based on the output.
 */
public class ConsoleRunnerImplTest {

  @Rule
  public TemporaryFolder temporary = new TemporaryFolder();

  private boolean failFast;
  private ConsoleRunnerImpl.OutputMode outputMode;
  private boolean xmlReport;
  private File outdir;
  private boolean perTestTimer;
  private Concurrency defaultConcurrency;
  private int parallelThreads;
  private int testShard;
  private int numTestShards;
  private int numRetries;
  private boolean useExperimentalRunner;

  @Before
  public void setUp() {
    resetParameters();
    ConsoleRunnerImpl.setCallSystemExitOnFinish(false);
    ConsoleRunnerImpl.addTestListener(null);
  }

  @After
  public void tearDown() {
    ConsoleRunnerImpl.setCallSystemExitOnFinish(true);
    ConsoleRunnerImpl.addTestListener(null);
  }

  private void resetParameters() {
    failFast = false;
    outputMode = ConsoleRunnerImpl.OutputMode.ALL;
    xmlReport = false;
    try {
      outdir = temporary.newFolder();
    } catch (IOException e) {
      throw new RuntimeException(e);
    }
    perTestTimer = false;
    defaultConcurrency = Concurrency.SERIAL;
    parallelThreads = 0;
    testShard = 0;
    numTestShards = 0;
    numRetries = 0;
    useExperimentalRunner = false;
  }

  private String runTestExpectingSuccess(Class testClass) {
    JSecMgrConfig securityConfig = new JSecMgrConfig(SystemExitHandling.disallow, ThreadHandling.disallowDanglingTestCaseThreads);
    return runTests(Lists.newArrayList(testClass.getCanonicalName()), false, securityConfig);
  }

  private String runTestExpectingFailure(Class<?> testClass) {
    JSecMgrConfig securityConfig = new JSecMgrConfig(SystemExitHandling.disallow, ThreadHandling.disallowDanglingTestCaseThreads);
    return runTests(Lists.newArrayList(testClass.getCanonicalName()), true, securityConfig);
  }

  private String runTestsExpectingSuccess(JSecMgrConfig secMgrConfig, Class<?> testClass) {
    return runTests(Lists.newArrayList(testClass.getCanonicalName()), false, secMgrConfig);
  }

  private String runTestsExpectingFailure(JSecMgrConfig secMgrConfig, Class<?> testClass) {
    return runTests(Lists.newArrayList(testClass.getCanonicalName()), true, secMgrConfig);
  }

  private String runTests(List<String> tests, boolean shouldFail, JSecMgrConfig config) {
    PrintStream originalOut = System.out;
    PrintStream originalErr = System.err;

    ByteArrayOutputStream outContent = new ByteArrayOutputStream();
    PrintStream quoteOriginalOut = new PrintStream(outContent, true);
    JSecMgr jSecMgr = new JSecMgr(config, quoteOriginalOut);
    try {
      System.setSecurityManager(jSecMgr);
      ConsoleRunnerImpl runner = new ConsoleRunnerImpl(
          failFast,
          outputMode,
          xmlReport,
          perTestTimer,
          outdir,
          defaultConcurrency,
          parallelThreads,
          testShard,
          numTestShards,
          numRetries,
          useExperimentalRunner,
          quoteOriginalOut,
          System.err, // TODO, if there's an error reported on system err, it doesn't show up in
                      // the test failures.
          jSecMgr);

      try {
        runner.run(tests);
        if (shouldFail) {
          fail("Expected RuntimeException");
        }
      } catch (StoppedByUserException e) {
        originalOut.println("runtime e " + e);
        if (!shouldFail) {
          throw e;
        }
      } catch (RuntimeException e) {
        originalOut.println("runtime e " + e);

        if (!shouldFail || !(e.getMessage() != null && e.getMessage().contains("ConsoleRunner exited with status"))) {
          throw e;
        }
      }
      quoteOriginalOut.flush();
      try {
        return outContent.toString(Charsets.UTF_8.toString());
      } catch (UnsupportedEncodingException e) {
        throw new RuntimeException(e);
      }
    } finally {

      // there might be a better way to do this.
      if (jSecMgr.anyHasDanglingThreads()) {
        originalErr.println("had dangling threads, trying interrupt");
        jSecMgr.interruptDanglingThreads();
        if (jSecMgr.anyHasDanglingThreads()) {
          originalErr.println("there are still remaining threads, sleeping");
          try {
            Thread.sleep(100);
          } catch (InterruptedException e) {
            // ignore
          }
        }
      } else {
        originalErr.println("no remaining threads");
      }

      System.setOut(originalOut);
      System.setErr(originalErr);

      System.setSecurityManager(null); // TODO disallow this, but allow here, could also
                                       // TODO add a reset button to the sec mgr
    }
  }

  @Test
  public void testFailFast() {
    failFast = false;
    String output = runTestExpectingFailure(AllFailingTest.class);
    assertThat(output, containsString("There were 4 failures:"));
    assertThat(output, containsString("Tests run: 4,  Failures: 4"));

    failFast = true;
    output = runTestExpectingFailure(AllFailingTest.class);
    assertThat(output, containsString("There was 1 failure:"));
    assertThat(output, containsString("Tests run: 1,  Failures: 1"));
  }

  @Test
  public void testFailSystemExit() {
    Class<SecBoundarySystemExitTests> testClass = SecBoundarySystemExitTests.class;
    String output = runTestsExpectingFailure(
        new JSecMgrConfig(SystemExitHandling.disallow, ThreadHandling.allowAll),
        testClass);
    String testClassName = testClass.getCanonicalName();
    assertThat(output, containsString("directSystemExit(" + testClassName + ")"));
    assertThat(output, containsString("catchesSystemExit(" + testClassName + ")"));
    assertThat(output, containsString("exitInJoinedThread(" + testClassName + ")"));
    assertThat(output, containsString("exitInNotJoinedThread(" + testClassName + ")"));

    assertThat(output, containsString("There were 4 failures:"));
    assertThat(output, containsString("Tests run: 5,  Failures: 4"));
  }

  @Test
  public void testDisallowDanglingThreadStartedInTestCase() {
    Class<?> testClass = SecDanglingThreadFromTestCase.class;
    String output = runTestsExpectingFailure(
        new JSecMgrConfig(SystemExitHandling.disallow, ThreadHandling.disallowDanglingTestCaseThreads),
        testClass);
    // TODO This shouldn't use a java.lang.SecurityException for the failure
    // Also could say where the thread was started.
    assertThat(output, containsString("startedThread(" + testClass.getCanonicalName() + ")"));
    //assertThat(output, containsString("at foo"));
    assertThat(output, containsString("There was 1 failure:"));
    assertThat(output, containsString("Tests run: 1,  Failures: 1"));
  }

  @Test
  public void testWhenDanglingThreadsAllowedPassOnThreadStartedInTestCase() {
    JSecMgrConfig secMgrConfig = new JSecMgrConfig(SystemExitHandling.disallow, ThreadHandling.allowAll);
    String output = runTestsExpectingSuccess(secMgrConfig, SecDanglingThreadFromTestCase.class);
    assertThat(output, containsString("OK (1 test)"));
  }

  @Test
  public void testThreadStartedInBeforeTestAndJoinedAfter() {
    // Expect that of the two tests, only the test that fails due to an assertion failure will fail.
    // And that it fails due to that failure
    Class<?> testClass = ThreadStartedInBeforeTest.class;
    String output = runTestsExpectingFailure(
        new JSecMgrConfig(SystemExitHandling.disallow, ThreadHandling.disallowDanglingTestCaseThreads),
        testClass);
    // TODO This shouldn't use a java.lang.SecurityException for the failure
    // Also could say where the thread was started.
    assertThat(output, containsString("failing(" + testClass.getCanonicalName() + ")"));
    assertThat(output, containsString("java.lang.AssertionError: failing"));
    assertThat(output, containsString("There was 1 failure:"));
    assertThat(output, containsString("Tests run: 2,  Failures: 1"));
  }

  @Ignore
  @Test
  public void testThreadStartedInBeforeClassAndJoinedAfterClassWithPerSuiteThreadLife() {
    // Expect that of the two tests, only the test that fails due to an assertion failure will fail.
    // And that it fails due to that failure.
    Class<?> testClass = ThreadStartedInBeforeClassAndJoinedAfterTest.class;
    String output = runTestsExpectingFailure(
        new JSecMgrConfig(SystemExitHandling.disallow, ThreadHandling.disallowDanglingTestSuiteThreads),
        testClass);
    // TODO This shouldn't use a java.lang.SecurityException for the failure
    // Also could say where the thread was started.
    assertThat(output, containsString("failing(" + testClass.getCanonicalName() + ")"));
    assertThat(output, containsString("There was 1 failure:"));
    assertThat(output, containsString("Tests run: 2,  Failures: 1"));
  }

  @Ignore
  @Test
  public void testThreadStartedInBeforeClassAndNotJoinedAfterClassWithPerSuiteThreadLife() {
    // Expect that of the two tests, only the test that fails due to an assertion failure will fail.
    // And that it fails due to that failure.
    Class<?> testClass = ThreadStartedInBeforeClassAndNotJoinedAfterTest.class;
    String output = runTestsExpectingFailure(
        new JSecMgrConfig(SystemExitHandling.disallow, ThreadHandling.disallowDanglingTestSuiteThreads),
        testClass);
    // TODO This shouldn't use a java.lang.SecurityException for the failure
    // Also could say where the thread was started.
    assertThat(output, containsString("failingxx(" + testClass.getCanonicalName() + ")"));
    //assertThat(output, containsString("at foo"));
    assertThat(output, containsString("There were 2 failures:"));
    assertThat(output, containsString("Tests run: 2,  Failures: 2"));
  }

  // TODO
  // - Flag for per class thread lifetimes
  // -- Allow thread that lives beyond test case
  // -- allow thread started in before all
  // -- ??? thread started in static context
  // - annotation for ignoring threads started in class.

  // test other class spawns thread st the test class isn't in class context of secmgr
  @Test
  public void treatStaticSystemExitAsFailure() {
    // The question here is whether it should fail before running the tests. Right now it runs them,
    // but the resulting error is
    // java.lang.ExceptionInInitializerError
    // at sun.reflect.NativeConstructorAccessorImpl.newInstance0(Native Method)
    // ... 50 lines ...
    // Caused by: java.lang.SecurityException: System.exit calls are not allowed. context: TestSecurityContext{org.pantsbuild.tools.junit.lib.security.SecStaticSysExitTestCase#passingTest2, threadGroup=java.lang.ThreadGroup[name=org.pantsbuild.tools.junit.lib.security.SecStaticSysExitTestCase-m-passingTest2-Threads,maxpri=10], threadGroupActiveCt=0, failureException=null}
    // at org.pantsbuild.tools.junit.impl.security.JSecMgr.checkExit(JSecMgr.java:257)
    // I think it should either end with 0 tests run 1 error, or
    // 2 run, 2 error, with a better error than ExceptionInInitializerError
    Class<?> testClass = SecStaticSysExitTestCase.class;
    String output = runTestsExpectingFailure(
        new JSecMgrConfig(SystemExitHandling.disallow, ThreadHandling.disallowDanglingTestCaseThreads),
        testClass);

    assertThat(output, containsString("passingTest(" + testClass.getCanonicalName() + ")"));
    assertThat(output, containsString("System.exit calls are not allowed"));
    // should be 0 tests run 1 failure/error
    assertThat(output, containsString("There were 2 failures:"));
    assertThat(output, containsString("Tests run: 2,  Failures: 2"));
  }

  @Test
  public void testFailFastWithMultipleThreads() {
    failFast = false;
    parallelThreads = 8;
    String output = runTestExpectingFailure(AllFailingTest.class);
    assertThat(output, containsString("There were 4 failures:"));
    assertThat(output, containsString("Tests run: 4,  Failures: 4"));

    failFast = true;
    parallelThreads = 8;
    output = runTestExpectingFailure(AllFailingTest.class);
    assertThat(output, containsString("There was 1 failure:"));
    assertThat(output, containsString("Tests run: 1,  Failures: 1"));
  }

  @Test
  public void testPerTestTimer() {
    perTestTimer = false;
    String output = runTestExpectingSuccess(AllPassingTest.class);
    assertThat(output, containsString("...."));
    assertThat(output, containsString("OK (4 tests)"));
    assertThat(output, not(containsString("AllPassingTest")));

    perTestTimer = true;
    output = runTestExpectingSuccess(AllPassingTest.class);

    assertThat(output, containsString(
        "org.pantsbuild.tools.junit.lib.AllPassingTest#testPassesOne"));
    assertThat(output, containsString(
        "org.pantsbuild.tools.junit.lib.AllPassingTest#testPassesTwo"));
    assertThat(output, containsString(
        "org.pantsbuild.tools.junit.lib.AllPassingTest#testPassesThree"));
    assertThat(output, containsString(
        "org.pantsbuild.tools.junit.lib.AllPassingTest#testPassesFour"));
    assertThat(output, containsString("OK (4 tests)"));
    assertThat(output, not(containsString("....")));
  }

  @Test
  public void testOutputMode() {
    outputMode = ConsoleRunnerImpl.OutputMode.ALL;
    String output = runTestExpectingFailure(OutputModeTest.class);
    assertThat(output, containsString("There were 2 failures:"));
    assertThat(output, containsString("Output from passing test"));
    assertThat(output, containsString("Output from failing test"));
    assertThat(output, containsString("Output from error test"));
    assertThat(output, not(containsString("Output from ignored test")));
    assertThat(output, containsString("testFails(org.pantsbuild.tools.junit.lib.OutputModeTest)"));
    assertThat(output, containsString("testErrors(org.pantsbuild.tools.junit.lib.OutputModeTest)"));
    assertThat(output, containsString("Tests run: 3,  Failures: 2"));

    outputMode = ConsoleRunnerImpl.OutputMode.FAILURE_ONLY;
    output = runTestExpectingFailure(OutputModeTest.class);
    assertThat(output, containsString("There were 2 failures:"));
    assertThat(output, not(containsString("Output from passing test")));
    assertThat(output, containsString("Output from failing test"));
    assertThat(output, containsString("Output from error test"));
    assertThat(output, not(containsString("Output from ignored test")));
    assertThat(output, containsString("testFails(org.pantsbuild.tools.junit.lib.OutputModeTest)"));
    assertThat(output, containsString("testErrors(org.pantsbuild.tools.junit.lib.OutputModeTest)"));
    assertThat(output, containsString("Tests run: 3,  Failures: 2"));

    outputMode = ConsoleRunnerImpl.OutputMode.NONE;
    output = runTestExpectingFailure(OutputModeTest.class);
    assertThat(output, containsString("There were 2 failures:"));
    assertThat(output, not(containsString("Output from passing test")));
    assertThat(output, not(containsString("Output from failing test")));
    assertThat(output, not(containsString("Output from error test")));
    assertThat(output, not(containsString("Output from ignored test")));
    assertThat(output, containsString("testFails(org.pantsbuild.tools.junit.lib.OutputModeTest)"));
    assertThat(output, containsString("testErrors(org.pantsbuild.tools.junit.lib.OutputModeTest)"));
    assertThat(output, containsString("Tests run: 3,  Failures: 2"));
  }

  @Test
  public void testOutputModeExceptionInBefore() {
    outputMode = ConsoleRunnerImpl.OutputMode.ALL;
    String output = runTestExpectingFailure(ExceptionInSetupTest.class);
    assertThat(output, containsString("There was 1 failure:"));
    assertThat(output, containsString("java.lang.RuntimeException"));
    assertThat(output, containsString("Tests run: 0,  Failures: 1"));
    assertThat(output, not(containsString("Test mechanism")));

    outputMode = ConsoleRunnerImpl.OutputMode.FAILURE_ONLY;
    output = runTestExpectingFailure(ExceptionInSetupTest.class);
    assertThat(output, containsString("There was 1 failure:"));
    assertThat(output, containsString("java.lang.RuntimeException"));
    assertThat(output, containsString("Tests run: 0,  Failures: 1"));
    assertThat(output, not(containsString("Test mechanism")));

    outputMode = ConsoleRunnerImpl.OutputMode.NONE;
    output = runTestExpectingFailure(ExceptionInSetupTest.class);
    assertThat(output, containsString("There was 1 failure:"));
    assertThat(output, containsString("java.lang.RuntimeException"));
    assertThat(output, containsString("Tests run: 0,  Failures: 1"));
    assertThat(output, not(containsString("Test mechanism")));
  }

  /**
   * This test reproduces a problem reported in https://github.com/pantsbuild/pants/issues/3638
   */
  @Test
  public void testRunFinishFailed() throws Exception {
    class AbortInTestRunFinishedListener extends RunListener {
      @Override public void testRunFinished(Result result) throws Exception {
        throw new IOException("Bogus IOException");
      }
    }
    ConsoleRunnerImpl.addTestListener(new AbortInTestRunFinishedListener());

    String output = runTestExpectingFailure(AllPassingTest.class);
    assertThat(output, containsString("OK (4 tests)"));
    assertThat(output, containsString("java.io.IOException: Bogus IOException"));
  }
}
