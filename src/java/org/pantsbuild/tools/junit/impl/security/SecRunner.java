package org.pantsbuild.tools.junit.impl.security;

import java.util.HashMap;
import java.util.Map;
import java.util.logging.Logger;

import org.junit.runner.Description;
import org.junit.runner.Result;
import org.junit.runner.Runner;
import org.junit.runner.notification.Failure;
import org.junit.runner.notification.RunListener;
import org.junit.runner.notification.RunNotifier;

public class SecRunner extends Runner {
  private static Logger logger = Logger.getLogger("pants-junit");
  private final Runner wrappedRunner;
  private final JSecMgr secMgr;

  public SecRunner(Runner wrappedRunner, JSecMgr secMgr) {
    this.wrappedRunner = wrappedRunner;
    this.secMgr = secMgr;
  }

  @Override public Description getDescription() {
    return wrappedRunner.getDescription();
  }

  @Override public void run(RunNotifier notifier) {
    logger.fine("before add seclistener");
    // SecListener needs to be the first listener, otherwise the failures it fires will not be
    // in the xml results or the console output. This is because those are constructed with
    // listeners.
    notifier.addFirstListener(new SecListener(notifier, secMgr));
    log("after add seclistener");
    wrappedRunner.run(notifier);
    log("After wrapped runner");
  }

  private static void log(String s) {
    logger.fine(s);
  }

  public enum TestState {
    started,
    failed,
    danglingThreads
  }

  public static class SecListener extends RunListener {
    private final RunNotifier runNotifier;
    //private final Result result = new Result();
    private final Map<Description, TestState> tests =  new HashMap<>();
    private final JSecMgr secMgr;
    // think I need the RunNofifier here after all to trigger a failure.

    SecListener(RunNotifier runNotifier, JSecMgr secMgr) {
      this.runNotifier = runNotifier;
      this.secMgr = secMgr;
    }

    @Override
    public void testRunStarted(Description description) throws Exception {
      // might want to have a nested settings here in the manager
      super.testRunStarted(description);
      //secMgr.startTestClass(new JSecMgr.SuiteTestSecurityContext(description.getClassName()));
    }

    @Override
    public void testRunFinished(Result result) throws Exception {
      for (Map.Entry<Description, TestState> descriptionTestStateEntry : tests.entrySet()) {
        if (descriptionTestStateEntry.getValue() == TestState.danglingThreads) {
          if (secMgr.hadSecIssue(descriptionTestStateEntry.getKey().getClassName())) {
            log("found sec issue in dangling thread test.");
            runNotifier.fireTestFailure(new Failure(descriptionTestStateEntry.getKey(),
                secMgr.contextFor(descriptionTestStateEntry.getKey().getClassName()).getFailures().iterator().next()));
          }
        }

      }
      if (secMgr.anyHasDanglingThreads()) {
        log("has dangling threads! ");
        //Map.Entry<Description, TestState> next = tests.entrySet().iterator().next();
        //runNotifier.fireTestFailure(new Failure(next.getKey(), new Exception("has dangling threads")));
        //runNotifier.fireTestFailure(new Failure(new Description()));
      } else {
        log("All good then");
      }
    }

    @Override
    public void testStarted(Description description) throws Exception {
      super.testStarted(description);
      log("test-started: "+description);
      secMgr.startTest(new JSecMgr.TestCaseSecurityContext(description.getClassName(),
                                                     description.getMethodName()));
      tests.put(description, TestState.started);
    }

    @Override
    public void testFailure(Failure failure) throws Exception {
      //description.
      // if not failed and there was a sec issue and we're failing on them, raise an exception
      tests.put(failure.getDescription(), TestState.failed);
    }

    @Override
    public void testAssumptionFailure(Failure failure) {
      tests.put(failure.getDescription(), TestState.failed);
    }

    @Override
    public void testFinished(Description description) throws Exception {
      // check for dangling resources here
      log("finished test " + description);
      try {
        TestState testState = tests.get(description);
        if (testState == TestState.failed) {
          log("Listener here: already had failed");
          // pass -- we're already failing
          // note, might be worth checking why it failed and printing something
        } else if (secMgr.hadSecIssue(description.getClassName())) {
          Throwable cause = secMgr.securityIssue();
          log("Listener here: had sec issue, " + cause);
          log("\n     settings: "+ secMgr.contextFor(description.getClassName()));
          if (cause == null) {
            cause = new RuntimeException("think it should have failed anyway. " +
                "Think probably shouldnt get here");
          }

          runNotifier.fireTestFailure(new Failure(description, cause));
          // if secmgr thinks it should have failed, then fail it.
        }
        if (secMgr.hasDanglingThreads(description.getClassName())) {
          log("has dangling threads! " + description);
          if (secMgr.config.disallowDanglingThread()) {
            runNotifier.fireTestFailure(new Failure(
                description,
                new SecurityException("Threads from "+description+" are still running.")));
          } else {
            tests.put(description, TestState.danglingThreads);
          }
        } else {
          log("Listener here: no issues");
        }
      } finally {
        secMgr.endTest();
      }
      //description.
      // if not failed and there was a sec issue and we're failing on them, raise an exception
    }

    private void log(String x) {
      logger.fine("-SecListener-  " + x);
    }
  }
}
