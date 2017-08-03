package org.pantsbuild.tools.junit.impl.security;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
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
    // todo can this be run on different threads? If so, I need some rethinking.
    private final Map<Description, TestState> tests =  new HashMap<>();
    private final JSecMgr secMgr;

    SecListener(RunNotifier runNotifier, JSecMgr secMgr) {
      this.runNotifier = runNotifier;
      this.secMgr = secMgr;
    }

    @Override
    public void testRunStarted(Description description) throws Exception {
      // might want to have a nested settings here in the manager
    }


    // testRunFinished is for all of the tests.
    @Override
    public void testRunFinished(Result result) throws Exception {
      System.out.println("Z");
      for (Description description : tests.keySet()) {
        if (tests.get(description) == TestState.failed) {
          // NB if it's already failed, just show the initial
          // failure.
          continue;
        }

        TestSecurityContext context = contextFor(description);
        if (description.isTest()) {
          if (context.hadFailures()) {
            handleSecurityFailure(description, context);
          }
          handleDanglingThreads(description, context);
        } else if (description.isSuite()) {
          if (context.hadFailures()) {
            handleSecurityFailure(description, context);
          }
          handleDanglingThreads(description, context);
        } else {
          throw new RuntimeException("WUT " + description);
        }
      }

      Set<Class<?>> classNames = new HashSet<>();
      for (Description description : tests.keySet()) {
        classNames.add(description.getTestClass());
      }
      for (Class<?> className : classNames) {
        TestSecurityContext context = secMgr.contextFor(className.getCanonicalName());
        if (context != null) {
          if (context.hadFailures()) {
            handleSecurityFailure(Description.createSuiteDescription(className), context);
          }
          if (secMgr.perClassThreadHandling()) {
            handleDanglingThreads(Description.createSuiteDescription(className), context);
          }
        }
      }

    }

    @Override
    public void testStarted(Description description) throws Exception {
      log("test-started: "+description);
      if (description.isTest()) {
        secMgr.startTest(new TestSecurityContext.TestCaseSecurityContext(description.getClassName(),
            description.getMethodName(), secMgr.contextFor(description.getClassName())));
      } else if (description.isSuite()){
        secMgr.startSuite(description.getClassName());
      } else {
        log("what is "+description);
      }
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
      TestState testState = tests.get(description);
      if (testState == TestState.failed) {
        // NB if it's already failed, just show the initial
        // failure.
        return;
      }

      TestSecurityContext context = contextFor(description);
      if (description.isTest()) {
        try {
          if (context.hadFailures()) {
            handleSecurityFailure(description, context);
          }
          handleDanglingThreads(description, context);
        } finally {
          secMgr.endTest();
        }
      } else if (description.isSuite()) {
        if (context.hadFailures()) {
          handleSecurityFailure(description, context);
        }
        handleDanglingThreads(description, context);
      }

      //description.
      // if not failed and there was a sec issue and we're failing on them, raise an exception
    }

    public void handleSecurityFailure(Description description, TestSecurityContext context) {
      if (tests.get(description) == TestState.failed) {
        return;
      }
      Throwable cause = context.firstFailure();
      fireFailure(description, cause);
      tests.put(description, TestState.failed);
    }

    public void handleDanglingThreads(Description description, TestSecurityContext context) {
      if (context.hasActiveThreads()) {
        if(secMgr.disallowsThreadsFor(context)) {
          fireFailure(description, new SecurityException("Threads from " + description + " are still running."));
          tests.put(description, TestState.failed);
        } else {
          tests.put(description, TestState.danglingThreads);
        }
      }
    }

    private void fireFailure(Description description, Throwable cause) {
      runNotifier.fireTestFailure(new Failure(description, cause));
    }

    public TestSecurityContext contextFor(Description description) {
      return secMgr.contextFor(description.getClassName(), description.getMethodName());
    }

    private void log(String x) {
      logger.fine("-SecListener-  " + x);
    }
  }
}
